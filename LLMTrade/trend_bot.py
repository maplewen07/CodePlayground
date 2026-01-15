import os
import json
import time
from typing import Any, Dict, List, Optional, Tuple

from config import BotConfig
from okx_client import OKXClient
from llm_filter import LLMFilter
from indicators import ema, atr
from state_manager import load_state, save_state


class TrendBot:
    def __init__(self, cfg: BotConfig, client: OKXClient, llm: LLMFilter):
        self.cfg = cfg
        self.client = client
        self.llm = llm
        self.state_path = "state.json"
        self.state = load_state(self.state_path)

        # 交易对规则（最小下单数量/步进），来自 instruments
        inst = self.client.get_instruments_spot(cfg.inst_id)
        # 常见字段：minSz, lotSz（不同站点字段可能略差异，拿不到就级降）
        self.min_sz = float(inst.get("minSz", "0.0001"))
        self.lot_sz = float(inst.get("lotSz", "0.00000001"))

    def _round_sz(self, sz: float) -> float:
        # 向下取整到 lotSz
        steps = int(sz / self.lot_sz)
        r = steps * self.lot_sz
        return float(f"{r:.12f}")

    def _get_last_price_and_atr(self) -> Tuple[float, float, float, float]:
        candles = self.client.get_candles(self.cfg.inst_id, self.cfg.bar, self.cfg.candle_limit)
        # candles: 最近在前 -> 翻转为时间正序
        candles = list(reversed(candles))
        closes = [float(x[4]) for x in candles]
        highs = [float(x[2]) for x in candles]
        lows  = [float(x[3]) for x in candles]

        ef = ema(closes, self.cfg.ema_fast)
        es = ema(closes, self.cfg.ema_slow)
        a  = atr(highs, lows, closes, self.cfg.atr_len)

        last = closes[-1]
        last_ef = ef[-1] if ef else float("nan")
        last_es = es[-1] if es else float("nan")
        last_atr = a[-1] if a else float("nan")
        return last, last_ef, last_es, last_atr

    def _get_spot_balances(self) -> Tuple[float, float]:
        # 简化：只取 BTC 和 USDT
        b_btc = self.client.get_balance("BTC")
        b_usdt = self.client.get_balance("USDT")

        def parse_avail(balance_resp: Dict[str, Any], ccy: str) -> float:
            # data[0].details[] 里找 ccy；字段常见为 availBal
            try:
                details = balance_resp["data"][0].get("details", [])
                for d in details:
                    if d.get("ccy") == ccy:
                        return float(d.get("availBal", "0"))
            except Exception:
                pass
            return 0.0

        return parse_avail(b_btc, "BTC"), parse_avail(b_usdt, "USDT")

    def _place_market_buy_usdt(self, usdt_amount: float) -> Dict[str, Any]:
        # 现货市价买：sz 默认按 quote_ccy（USDT） 
        usdt_amount = float(usdt_amount)
        return self.client.place_order(
            inst_id=self.cfg.inst_id,
            side="buy",
            ord_type="market",
            sz=f"{usdt_amount:.6f}",
            td_mode="cash",
            tgt_ccy="quote_ccy",
        )

    def _place_limit_sell_btc(self, btc_sz: float, px: float) -> Dict[str, Any]:
        btc_sz = self._round_sz(btc_sz)
        if btc_sz < self.min_sz:
            raise RuntimeError(f"sell size too small: {btc_sz} < minSz {self.min_sz}")
        return self.client.place_order(
            inst_id=self.cfg.inst_id,
            side="sell",
            ord_type="limit",
            sz=f"{btc_sz:.12f}",
            px=f"{px:.2f}",
            td_mode="cash",
            tgt_ccy="base_ccy",
        )

    def _cancel_algo_if_any(self, algo_key: str) -> None:
        algo_id = self.state.get(algo_key)
        if not algo_id:
            return
        try:
            self.client.cancel_advance_algos([{"algoId": str(algo_id), "instId": self.cfg.inst_id}])
        except Exception:
            pass
        self.state[algo_key] = None

    def _place_or_update_trailing_stop(self, btc_remaining: float, last_price: float, last_atr: float) -> None:
        # 思路：对“剩余仓位”放一个追踪止损
        btc_remaining = self._round_sz(btc_remaining)
        if btc_remaining < self.min_sz:
            return

        trail_dist = self.cfg.trail_atr_mult * last_atr
        stop_trigger = max(0.0, last_price - trail_dist)

        # 先取消旧的追踪/止损策略单
        if self.cfg.use_exchange_trailing_algo:
            self._cancel_algo_if_any("trail_algo_id")

            # 使用 move_order_stop（追踪策略单），参数说明在文档里给了 callbackRatio/activePx/moveTriggerPx 
            # callbackRatio：回撤百分比（这里用 ATR 距离换算为百分比）
            callback_ratio = (trail_dist / last_price) * 100.0
            body = {
                "instId": self.cfg.inst_id,
                "tdMode": "cash",
                "side": "sell",
                "ordType": "move_order_stop",
                "sz": f"{btc_remaining:.12f}",
                "tgtCcy": "base_ccy",
                "callbackRatio": f"{callback_ratio:.4f}",
                "activePx": f"{last_price:.2f}",
                "moveTriggerPx": f"{last_price:.2f}",
                # 注意：不同账号/站点可能还需要其它字段；若报错，建议改用本地追踪模式
            }
            resp = self.client.place_algo_order(body)
            # 返回里通常有 algoId（模板：尽力取）
            algo_id = None
            try:
                algo_id = resp["data"][0].get("algoId")
            except Exception:
                pass
            self.state["trail_algo_id"] = algo_id
        else:
            # 本地追踪：每小时重新下一个 conditional 止损（slOrdPx=-1 表示市价止损） 
            self._cancel_algo_if_any("sl_algo_id")

            body = {
                "instId": self.cfg.inst_id,
                "tdMode": "cash",
                "side": "sell",
                "ordType": "conditional",
                "sz": f"{btc_remaining:.12f}",
                "tgtCcy": "base_ccy",
                "slTriggerPx": f"{stop_trigger:.2f}",
                "slOrdPx": "-1",
                "slTriggerPxType": "last",
            }
            resp = self.client.place_algo_order(body)
            algo_id = None
            try:
                algo_id = resp["data"][0].get("algoId")
            except Exception:
                pass
            self.state["sl_algo_id"] = algo_id

    def run_once(self) -> None:
        last_price, ef, es, last_atr = self._get_last_price_and_atr()
        if any(map(lambda x: x != x, [ef, es, last_atr])):  # NaN 检测
            print("指标数据不足，等待更多K线…")
            return

        btc_avail, usdt_avail = self._get_spot_balances()
        pos_btc = btc_avail

        in_uptrend = ef > es
        payload_for_llm = {
            "instId": self.cfg.inst_id,
            "bar": self.cfg.bar,
            "last_price": last_price,
            "ema_fast": ef,
            "ema_slow": es,
            "atr": last_atr,
            "pos_btc": pos_btc,
            "usdt_avail": usdt_avail,
        }
        if not self.llm.allow_trade(payload_for_llm):
            print("LLM 过滤：本轮不交易")
            return

        # ====== 入场/加仓状态 ======
        tranche_idx = int(self.state.get("tranche_idx", 0))
        last_add_time_ms = int(self.state.get("last_add_time_ms", 0))

        now_ms = self.client.get_server_time_ms()  # 用服务器时间更稳 
        hours_since_add = (now_ms - last_add_time_ms) / 3600000.0 if last_add_time_ms else 1e9

        invested = float(self.state.get("invested_quote", 0.0))
        entry_ref = float(self.state.get("entry_ref_price", last_price))  # 用于判断回撤加仓

        # ====== 趋势跟随逻辑（示例） ======
        if in_uptrend:
            # 1) 若没有持仓，做第一笔
            if pos_btc <= 0.0 and tranche_idx < len(self.cfg.tranche_quotes):
                q = self.cfg.tranche_quotes[tranche_idx]
                if invested + q <= self.cfg.max_total_quote and usdt_avail >= q:
                    print(f"[ENTRY] 趋势向上，市价买入 {q} USDT")
                    self._place_market_buy_usdt(q)
                    self.state["tranche_idx"] = tranche_idx + 1
                    self.state["invested_quote"] = invested + q
                    self.state["last_add_time_ms"] = now_ms
                    self.state["entry_ref_price"] = last_price

            # 2) 若已有仓位，回撤加仓（趋势内回撤）
            elif pos_btc > 0.0 and tranche_idx < len(self.cfg.tranche_quotes):
                pullback = max(0.0, entry_ref - last_price)
                need_pullback = self.cfg.add_on_pullback_atr * last_atr
                if pullback >= need_pullback and hours_since_add >= self.cfg.min_hours_between_adds:
                    q = self.cfg.tranche_quotes[tranche_idx]
                    if invested + q <= self.cfg.max_total_quote and usdt_avail >= q:
                        print(f"[ADD] 回撤 {pullback:.2f} >= {need_pullback:.2f}，加仓 {q} USDT")
                        self._place_market_buy_usdt(q)
                        self.state["tranche_idx"] = tranche_idx + 1
                        self.state["invested_quote"] = invested + q
                        self.state["last_add_time_ms"] = now_ms
                        # 更新参考价：用最新价作为下一次回撤锚点
                        self.state["entry_ref_price"] = last_price

        else:
            # 趋势转弱：这里模板不强制清仓（因为你要“趋势跟随 + 追踪止损”）
            print("[INFO] EMA 快线 <= 慢线：趋势不强，暂停加仓，仅维护止盈/止损")

        # ====== 部分止盈 + 剩余追踪 ======
        # 简化：当持仓存在时，挂一个 tp1 限价卖 + 对剩余放追踪止损
        btc_avail, usdt_avail = self._get_spot_balances()
        pos_btc = btc_avail
        if pos_btc > 0.0:
            # tp1 只挂一次
            if not self.state.get("tp1_placed"):
                tp1_px = last_price * (1.0 + self.cfg.tp1_pct)
                tp1_sz = pos_btc * self.cfg.tp1_sell_pct
                tp1_sz = self._round_sz(tp1_sz)

                if tp1_sz >= self.min_sz:
                    try:
                        print(f"[TP1] 挂限价卖出 {tp1_sz} BTC @ {tp1_px:.2f}")
                        self._place_limit_sell_btc(tp1_sz, tp1_px)
                        self.state["tp1_placed"] = True
                    except Exception as e:
                        print(f"[WARN] TP1 下单失败：{e}")

            # 对“剩余仓位”做追踪（每次 run_once 都会更新一次）
            btc_avail, _ = self._get_spot_balances()
            remaining = btc_avail * (1.0 - self.cfg.tp1_sell_pct) if self.state.get("tp1_placed") else btc_avail
            remaining = max(0.0, remaining)

            if remaining >= self.min_sz:
                print(f"[TRAIL] 维护追踪止损（remaining={remaining:.8f} BTC, ATR={last_atr:.2f})")
                try:
                    self._place_or_update_trailing_stop(remaining, last_price, last_atr)
                except Exception as e:
                    print(f"[WARN] 追踪止损维护失败：{e}")

        save_state(self.state_path, self.state)