下面给你一份**可直接复制运行的 Python 单文件模板**（OKX 现货 / BTC / 小时级 / 趋势跟随 / 分批加仓 / 部分止盈 + 剩余追踪）。  
它用 **OKX V5 REST**：签名规则是 `timestamp + method + requestPath + body` 做 HMAC-SHA256 再 Base64（请求头含 `OK-ACCESS-KEY/SIGN/TIMESTAMP/PASSPHRASE`） ；下单 `POST /api/v5/trade/order` ；K线 `GET /api/v5/market/candles` ；服务器时间 `GET /api/v5/public/time` ；止盈止损/追踪可用策略单 `POST /api/v5/trade/order-algo`，其中包含 `conditional/oco/move_order_stop(追踪)` 等 。

> 重要提醒：这只是“模板 + 基础风控骨架”，不保证盈利，实盘有滑点/手续费/断网/接口限频/极端行情等风险；建议先跑模拟盘/小资金。

---

## 用法（3步）
1) 安装依赖
```bash
pip install requests
```

2) 设置环境变量（也可以直接在代码里填）
- `OKX_API_KEY`
- `OKX_API_SECRET`
- `OKX_API_PASSPHRASE`

3) 运行
```bash
python okx_spot_trend_bot.py
```

---

## ✅ 单文件代码：`okx_spot_trend_bot.py`
```python
import os
import json
import time
import hmac
import base64
import hashlib
import datetime as dt
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests


# =========================
# 配置区（按你策略改这里就够）
# =========================
@dataclass
class BotConfig:
    base_url: str = "https://www.okx.com"   # OKX 主站。若你账号在 EEA/US 分站，需换成对应域名
    inst_id: str = "BTC-USDT"              # 现货
    bar: str = "1H"                        # 小时级
    candle_limit: int = 200

    # 趋势：EMA 快慢线
    ema_fast: int = 20
    ema_slow: int = 50
    atr_len: int = 14

    # 仓位与加仓（用 USDT 计）
    max_total_quote: float = 300.0         # 最大投入 USDT（你自己改）
    tranche_quotes: Tuple[float, ...] = (100.0, 100.0, 100.0)  # 分3批
    add_on_pullback_atr: float = 0.8       # 回撤 >= 0.8*ATR 才考虑加仓（趋势内回撤加）
    min_hours_between_adds: int = 2        # 加仓冷却

    # 止盈与追踪
    tp1_pct: float = 0.012                # 第一段止盈：+1.2%
    tp1_sell_pct: float = 0.35            # 卖出35%，剩余继续追踪
    trail_atr_mult: float = 2.2           # 追踪止损距离 = 2.2*ATR
    use_exchange_trailing_algo: bool = False
    # True：尝试用 move_order_stop（追踪策略单）
    # False：用“本地追踪”= 每小时更新一次 conditional 止损单（更稳/更可控）

    # 大模型过滤（模板：你把这里接上自己的模型）
    enable_llm_filter: bool = False


# =========================
# OKX REST 客户端（签名/请求）
# =========================
class OKXClient:
    def __init__(self, api_key: str, api_secret: str, passphrase: str, base_url: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    @staticmethod
    def _iso_timestamp_utc() -> str:
        # OKX/OKCoin 文档示例为毫秒 ISO8601：2020-12-08T09:08:57.715Z 
        now = dt.datetime.utcnow()
        return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(now.microsecond/1000):03d}Z"

    def _sign(self, timestamp: str, method: str, request_path: str, body: str) -> str:
        # sign = Base64(HMAC_SHA256(secret, timestamp + method + requestPath + body)) 
        prehash = f"{timestamp}{method.upper()}{request_path}{body}"
        mac = hmac.new(self.api_secret.encode("utf-8"), prehash.encode("utf-8"), hashlib.sha256)
        return base64.b64encode(mac.digest()).decode()

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None,
                 body: Optional[Dict[str, Any]] = None, auth: bool = False,
                 retry: int = 2) -> Dict[str, Any]:
        method = method.upper()
        params = params or {}
        body = body or {}

        # 组装 requestPath（GET 参数算在 requestPath，不算 body） 
        if method == "GET" and params:
            qs = "&".join([f"{k}={params[k]}" for k in params])
            request_path = f"{path}?{qs}"
        else:
            request_path = path

        body_str = "" if method == "GET" else json.dumps(body, separators=(",", ":"), ensure_ascii=False)

        headers = {}
        if auth:
            ts = self._iso_timestamp_utc()
            sign = self._sign(ts, method, request_path, body_str)
            headers.update({
                "OK-ACCESS-KEY": self.api_key,
                "OK-ACCESS-SIGN": sign,
                "OK-ACCESS-TIMESTAMP": ts,
                "OK-ACCESS-PASSPHRASE": self.passphrase,
            })

        url = self.base_url + request_path

        last_err = None
        for attempt in range(retry + 1):
            try:
                if method == "GET":
                    r = self.session.get(url, headers=headers, timeout=10)
                else:
                    r = self.session.post(self.base_url + path, headers=headers, data=body_str, timeout=10)

                data = r.json()
                # OKX/OKCoin 通常 code=="0" 表示成功
                if str(data.get("code")) == "0":
                    return data

                # 常见：接口偶发超时/压力（官方 FAQ 也建议错峰/重试） 
                last_err = RuntimeError(f"API error code={data.get('code')} msg={data.get('msg')} data={data.get('data')}")
            except Exception as e:
                last_err = e

            if attempt < retry:
                time.sleep(0.6 * (attempt + 1))

        raise last_err

    # ---------- 公共数据 ----------
    def get_server_time_ms(self) -> int:
        # GET /api/v5/public/time 
        data = self._request("GET", "/api/v5/public/time", auth=False)
        return int(data["data"][0]["ts"])

    def get_candles(self, inst_id: str, bar: str, limit: int) -> List[List[str]]:
        # GET /api/v5/market/candles 
        params = {"instId": inst_id, "bar": bar, "limit": str(limit)}
        data = self._request("GET", "/api/v5/market/candles", params=params, auth=False)
        # 返回：[[ts, o, h, l, c, vol, volCcy, ...], ...]，按“最近在前”
        return data["data"]

    def get_instruments_spot(self, inst_id: str) -> Dict[str, Any]:
        # GET /api/v5/public/instruments?instType=SPOT 
        params = {"instType": "SPOT", "instId": inst_id}
        data = self._request("GET", "/api/v5/public/instruments", params=params, auth=False)
        if not data["data"]:
            raise RuntimeError("Instrument not found, check instId.")
        return data["data"][0]

    # ---------- 私有数据 ----------
    def get_balance(self, ccy: str) -> Dict[str, Any]:
        # /api/v5/account/balance?ccy=BTC 等在文档签名示例中出现 
        params = {"ccy": ccy}
        return self._request("GET", "/api/v5/account/balance", params=params, auth=True)

    # ---------- 下单 ----------
    def place_order(self, inst_id: str, side: str, ord_type: str, sz: str,
                    px: Optional[str] = None, td_mode: str = "cash",
                    tgt_ccy: Optional[str] = None, cl_ord_id: Optional[str] = None) -> Dict[str, Any]:
        # POST /api/v5/trade/order 
        body = {
            "instId": inst_id,
            "tdMode": td_mode,
            "side": side,
            "ordType": ord_type,
            "sz": sz,
        }
        if px is not None:
            body["px"] = px
        if tgt_ccy is not None:
            body["tgtCcy"] = tgt_ccy
        if cl_ord_id is not None:
            body["clOrdId"] = cl_ord_id

        return self._request("POST", "/api/v5/trade/order", body=body, auth=True)

    def place_algo_order(self, body: Dict[str, Any]) -> Dict[str, Any]:
        # POST /api/v5/trade/order-algo 
        return self._request("POST", "/api/v5/trade/order-algo", body=body, auth=True)

    def cancel_advance_algos(self, items: List[Dict[str, str]]) -> Dict[str, Any]:
        # POST /api/v5/trade/cancel-advance-algos 
        return self._request("POST", "/api/v5/trade/cancel-advance-algos", body=items, auth=True)


# =========================
# 指标：EMA / ATR
# =========================
def ema(values: List[float], period: int) -> List[float]:
    if len(values) < period:
        return []
    k = 2.0 / (period + 1.0)
    out = []
    s = sum(values[:period]) / period
    out.extend([float("nan")] * (period - 1))
    out.append(s)
    for i in range(period, len(values)):
        s = values[i] * k + s * (1 - k)
        out.append(s)
    return out

def atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> List[float]:
    if len(closes) < period + 1:
        return []
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    # RMA/EMA-like 平滑
    out = [float("nan")] * period
    first = sum(trs[:period]) / period
    out.append(first)
    alpha = 1.0 / period
    s = first
    for i in range(period, len(trs)):
        s = (1 - alpha) * s + alpha * trs[i]
        out.append(s)
    return out


# =========================
# 大模型过滤（模板：你自己接入）
# =========================
class LLMFilter:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def allow_trade(self, payload: Dict[str, Any]) -> bool:
        """
        这里是“接口位”：你把 payload 发给大模型，大模型返回 JSON：
          {"allow": true/false, "reason": "..."}
        模板里默认永远允许（enabled=False 或未接入）
        """
        if not self.enabled:
            return True

        # TODO: 在这里接入你的大模型 API
        # 示例：return result_json.get("allow", False)
        return True


# =========================
# 策略状态（落地到 state.json）
# =========================
def load_state(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(path: str, state: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# =========================
# 核心策略：趋势跟随 + 分批加仓 + 部分止盈 + 追踪止损
# =========================
class TrendBot:
    def __init__(self, cfg: BotConfig, client: OKXClient, llm: LLMFilter):
        self.cfg = cfg
        self.client = client
        self.llm = llm
        self.state_path = "state.json"
        self.state = load_state(self.state_path)

        # 交易对规则（最小下单数量/步进），来自 instruments
        inst = self.client.get_instruments_spot(cfg.inst_id)
        # 常见字段：minSz, lotSz（不同站点字段可能略差异，拿不到就降级）
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


# =========================
# 主循环：对齐到每小时整点（简单可靠）
# =========================
def sleep_to_next_hour():
    now = dt.datetime.now()
    nxt = (now.replace(minute=0, second=5, microsecond=0) + dt.timedelta(hours=1))
    sec = (nxt - now).total_seconds()
    if sec > 0:
        time.sleep(sec)

def main():
    cfg = BotConfig()

    api_key = os.getenv("OKX_API_KEY", "").strip()
    api_secret = os.getenv("OKX_API_SECRET", "").strip()
    passphrase = os.getenv("OKX_API_PASSPHRASE", "").strip()
    if not (api_key and api_secret and passphrase):
        raise RuntimeError("请先设置环境变量 OKX_API_KEY / OKX_API_SECRET / OKX_API_PASSPHRASE")

    client = OKXClient(api_key, api_secret, passphrase, cfg.base_url)
    llm = LLMFilter(cfg.enable_llm_filter)
    bot = TrendBot(cfg, client, llm)

    print("Bot started. Running on hourly cadence.")
    while True:
        try:
            bot.run_once()
        except Exception as e:
            print(f"[ERROR] {e}")
        sleep_to_next_hour()


if __name__ == "__main__":
    main()
```

---

## 你接下来最建议改的 4 件事（实盘前）
1) **先用模拟盘/小资金**：把 `max_total_quote` 调到非常小。  
2) **确认你账号域名**：有些地区需要用对应站点域名（否则可能 401/签名通过但下单失败）。  
3) **把“成交确认”做严谨**：模板里用余额近似判断（简单但不完美），实盘最好补上“查订单/成交回报”。  
4) **大模型只做过滤器**：别让大模型直接决定下单数量/方向；让它输出结构化 JSON（allow/理由/风险提示），你再用规则策略执行，稳定性更好。

如果你愿意，我也可以在不改变你策略的前提下，把这个模板升级成：  
- 支持**只在新K线收盘后**才运行（避免小时内噪声）  
- 用 `Get order list / order details` 做**严格状态机**（TP1 是否成交、止损是否触发、策略单是否存在）  
- 加上**日志、断线重连、限频保护**（比如对错误码退避重试）