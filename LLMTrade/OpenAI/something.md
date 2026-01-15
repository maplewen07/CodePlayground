可以，用 Python 做“**小时级 BTC 现货趋势跟随 + 分批加仓（金字塔）**”是很典型、也比较工程友好的组合。下面给你一套**能直接照着写**的落地方案：规则引擎负责“能不能交易 + 分批加仓逻辑 + 风控”，大模型只做“分析/解释/可选的否决或微调”。

> 说明：下面是工程与策略框架，不构成投资建议；请先用模拟/小额验证。

---

## 1) 分批加仓（金字塔）怎么设计才不容易翻车
**原则：只在“盈利方向”加仓**，绝不越跌越加（那是摊平，不是趋势跟随）。

一套常用配置（小时级很合适）：

- **趋势判定**（程序端算，确定性强）
  - `EMA20 > EMA50` 且 `EMA20 slope > 0`
  - 过滤震荡：`ADX > 某阈值`（可选），或 `ema_spread_pct > 阈值`
- **入场**：首次买入 1 笔（tranche0）
- **加仓触发**：每次价格**相对上一次加仓价**上涨 `k * ATR`（比如 k=1.0~1.5）且趋势仍成立
- **加仓次数上限**：比如最多加 3 次（总 4 笔）
- **每笔仓位比例**（举例）
  - 40% / 30% / 20% / 10%（越往上越小，降低追高风险）
- **出场**（二选一或组合）
  - 趋势反转：`EMA20 < EMA50` → 清仓
  - **移动止损**（推荐）：`stop = highest_since_entry - m * ATR`（m=2~3），随着新高上移

---

## 2) 大模型放在哪：建议做“否决权/参数微调”，别做“直接下单权”
你可以让 LLM 每小时输出 JSON（例如 BUY/SELL/HOLD、建议仓位比例、风险等级、作废条件）。但最终执行用你的规则闸门：

- 低置信度 → 强制 HOLD
- 止损不合规 → 拒单
- 冷却期未到 → 拒单
- 加仓条件不满足 → 不加

这样即使 LLM 偶尔“编故事”，也不会直接把你带沟里。

---

## 3) Python 代码骨架（可直接改成实盘）
下面这份把关键模块都搭好了：指标→趋势→分批加仓→移动止损→风控→下单接口抽象。你只需要把 `ExchangeClient` 换成你交易所的 REST/WS 调用（或接入 ccxt 等库）。

```python
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List
import time
import math

import pandas as pd

# ---------- 配置 ----------
@dataclass
class StrategyConfig:
    symbol: str = "BTCUSDT"
    timeframe: str = "1h"
    ema_fast: int = 20
    ema_slow: int = 50
    atr_n: int = 14

    # 趋势过滤
    min_ema_spread_pct: float = 0.0015   # 0.15% 过滤震荡（可调）

    # 分批加仓（金字塔）
    max_adds: int = 3  # 在首次入场后，最多加仓次数
    tranche_weights: List[float] = None  # 默认 [0.4, 0.3, 0.2, 0.1]
    add_step_atr: float = 1.2            # 每上涨 1.2*ATR 触发下一次加仓

    # 风控
    max_total_allocation_usdt: float = 500.0  # 最多投入多少 USDT（你自己设）
    max_slippage_pct: float = 0.001           # 0.1% 超过就不市价追单（简化）
    cooldown_hours: int = 3

    # 移动止损
    trail_atr_mult: float = 2.5

    # LLM 输出闸门
    min_confidence: float = 0.60

    def __post_init__(self):
        if self.tranche_weights is None:
            self.tranche_weights = [0.4, 0.3, 0.2, 0.1]
        assert len(self.tranche_weights) == self.max_adds + 1
        assert abs(sum(self.tranche_weights) - 1.0) < 1e-6


@dataclass
class PositionState:
    btc_qty: float = 0.0
    avg_price: float = 0.0
    adds_done: int = 0
    last_add_price: float = 0.0
    highest_since_entry: float = 0.0
    stop_price: float = 0.0
    last_trade_ts: float = 0.0  # epoch seconds


# ---------- 指标 ----------
def ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()

def atr(df: pd.DataFrame, n: int) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def slope(series: pd.Series, lookback: int = 6) -> float:
    # 简化：用最近 lookback 根的差值当斜率
    if len(series) < lookback + 1:
        return 0.0
    return float(series.iloc[-1] - series.iloc[-1 - lookback])


# ---------- 规则信号（程序端主引擎） ----------
def compute_features(df: pd.DataFrame, cfg: StrategyConfig) -> Dict[str, Any]:
    c = df["close"]
    ema_f = ema(c, cfg.ema_fast)
    ema_s = ema(c, cfg.ema_slow)
    atr_v = atr(df, cfg.atr_n)

    close_now = float(c.iloc[-1])
    ema_fast_now = float(ema_f.iloc[-1])
    ema_slow_now = float(ema_s.iloc[-1])
    atr_now = float(atr_v.iloc[-1]) if not math.isnan(atr_v.iloc[-1]) else 0.0

    ema_spread_pct = (ema_fast_now - ema_slow_now) / ema_slow_now if ema_slow_now else 0.0
    ema_fast_slope = slope(ema_f, lookback=6)

    return {
        "close": close_now,
        "ema_fast": ema_fast_now,
        "ema_slow": ema_slow_now,
        "ema_spread_pct": ema_spread_pct,
        "ema_fast_slope": ema_fast_slope,
        "atr": atr_now,
        "atr_pct": atr_now / close_now if close_now else 0.0,
    }

def trend_is_up(feat: Dict[str, Any], cfg: StrategyConfig) -> bool:
    return (
        feat["ema_fast"] > feat["ema_slow"]
        and feat["ema_fast_slope"] > 0
        and feat["ema_spread_pct"] >= cfg.min_ema_spread_pct
    )

def trend_is_down(feat: Dict[str, Any]) -> bool:
    return feat["ema_fast"] < feat["ema_slow"]


# ---------- LLM（可选）：输出 JSON 建议 ----------
def llm_analyze_stub(features: Dict[str, Any], state: PositionState, cfg: StrategyConfig) -> Dict[str, Any]:
    """
    用你自己的 LLM 调用替换这里。建议让模型只输出 JSON：
    {
      "action":"BUY|SELL|HOLD",
      "confidence":0-1,
      "note":"...",
      "invalid_if":[...]
    }
    """
    # 默认：不干预，只给高置信度 HOLD（示例）
    return {"action": "HOLD", "confidence": 0.5, "invalid_if": []}


# ---------- 风控与仓位计算 ----------
def in_cooldown(state: PositionState, cfg: StrategyConfig) -> bool:
    if state.last_trade_ts <= 0:
        return False
    return (time.time() - state.last_trade_ts) < cfg.cooldown_hours * 3600

def tranche_usdt(cfg: StrategyConfig, tranche_idx: int) -> float:
    return cfg.max_total_allocation_usdt * cfg.tranche_weights[tranche_idx]

def update_trailing_stop(state: PositionState, feat: Dict[str, Any], cfg: StrategyConfig):
    if state.btc_qty <= 0:
        return
    state.highest_since_entry = max(state.highest_since_entry, feat["close"])
    # 移动止损：最高价 - m*ATR
    atr_now = feat["atr"]
    if atr_now > 0:
        new_stop = state.highest_since_entry - cfg.trail_atr_mult * atr_now
        state.stop_price = max(state.stop_price, new_stop)  # 只上移不下移


# ---------- 交易所接口（你需要实现） ----------
class ExchangeClient:
    def fetch_ohlcv_1h(self, symbol: str, limit: int = 300) -> pd.DataFrame:
        """
        返回 DataFrame: columns=[timestamp, open, high, low, close, volume]
        你需要用交易所 REST 实现。
        """
        raise NotImplementedError

    def fetch_balances(self) -> Dict[str, float]:
        """返回 {"BTC": qty, "USDT": qty}"""
        raise NotImplementedError

    def place_market_buy(self, symbol: str, usdt_amount: float) -> Dict[str, Any]:
        raise NotImplementedError

    def place_market_sell(self, symbol: str, btc_qty: float) -> Dict[str, Any]:
        raise NotImplementedError


# ---------- 核心决策循环 ----------
def on_hour_tick(ex: ExchangeClient, cfg: StrategyConfig, state: PositionState):
    df = ex.fetch_ohlcv_1h(cfg.symbol, limit=300)
    df = df.sort_values("timestamp").reset_index(drop=True)

    feat = compute_features(df, cfg)
    up = trend_is_up(feat, cfg)
    down = trend_is_down(feat)

    # 更新移动止损（持仓时）
    update_trailing_stop(state, feat, cfg)

    # LLM 建议（可选）
    llm = llm_analyze_stub(feat, state, cfg)
    llm_action = llm.get("action", "HOLD")
    llm_conf = float(llm.get("confidence", 0.0))

    # 统一：LLM 低置信度不参与
    llm_ok = llm_conf >= cfg.min_confidence

    # 退出条件：止损 or 趋势反转（LLM 可否决“卖出”一般没必要）
    if state.btc_qty > 0:
        if feat["close"] <= state.stop_price and state.stop_price > 0:
            if not in_cooldown(state, cfg):
                ex.place_market_sell(cfg.symbol, state.btc_qty)
                state.btc_qty = 0.0
                state.avg_price = 0.0
                state.adds_done = 0
                state.last_add_price = 0.0
                state.highest_since_entry = 0.0
                state.stop_price = 0.0
                state.last_trade_ts = time.time()
            return

        if down:
            if not in_cooldown(state, cfg):
                ex.place_market_sell(cfg.symbol, state.btc_qty)
                state.btc_qty = 0.0
                state.avg_price = 0.0
                state.adds_done = 0
                state.last_add_price = 0.0
                state.highest_since_entry = 0.0
                state.stop_price = 0.0
                state.last_trade_ts = time.time()
            return

    # 入场：无仓位 + 上升趋势 +（可选）LLM 同意或不反对
    if state.btc_qty <= 0 and up and not in_cooldown(state, cfg):
        if (not llm_ok) or (llm_ok and llm_action in ["BUY", "HOLD"]):
            usdt_amt = tranche_usdt(cfg, tranche_idx=0)
            # 你可以在这里加“滑点/价差检查”，简化略
            resp = ex.place_market_buy(cfg.symbol, usdt_amt)
            # 这里应以真实成交回报更新 qty/avg_price（简化先略）
            state.adds_done = 0
            state.last_add_price = feat["close"]
            state.highest_since_entry = feat["close"]
            state.stop_price = feat["close"] - cfg.trail_atr_mult * feat["atr"] if feat["atr"] > 0 else 0.0
            state.last_trade_ts = time.time()
        return

    # 加仓：已有仓位 + 仍然趋势向上 + 达到加仓阈值
    if state.btc_qty > 0 and up and state.adds_done < cfg.max_adds and not in_cooldown(state, cfg):
        atr_now = feat["atr"]
        if atr_now > 0:
            trigger_price = state.last_add_price + cfg.add_step_atr * atr_now
            if feat["close"] >= trigger_price:
                if (not llm_ok) or (llm_ok and llm_action in ["BUY", "HOLD"]):
                    tranche_idx = state.adds_done + 1
                    usdt_amt = tranche_usdt(cfg, tranche_idx=tranche_idx)
                    ex.place_market_buy(cfg.symbol, usdt_amt)
                    state.adds_done += 1
                    state.last_add_price = feat["close"]
                    # 加仓后继续上移止损
                    update_trailing_stop(state, feat, cfg)


# ---------- 调度：每小时整点运行 ----------
def run_loop(ex: ExchangeClient, cfg: StrategyConfig):
    state = PositionState()
    while True:
        now = time.localtime()
        # 简单整点触发：分钟=0 且 秒<5
        if now.tm_min == 0 and now.tm_sec < 5:
            try:
                on_hour_tick(ex, cfg, state)
            except Exception as e:
                # 生产建议写日志 + 告警
                print("ERROR:", e)
            time.sleep(10)
        time.sleep(1)
```

你需要补上的关键点（实盘必须做）：
- **成交回报更新**：买入后用“真实成交均价/数量”更新 `btc_qty`、`avg_price`
- **账户同步**：每次 tick 前从交易所拉一次余额/持仓，避免状态漂移
- **滑点/价差保护**：如果市价单预估滑点超阈值就改限价或放弃
- **日志与复盘**：保存 features、LLM 输出、每次交易原因、最终盈亏

---

## 4) 分批加仓参数怎么先选一个“稳妥起步”的
给你一个比较保守的起步组合（后续再优化）：
- `max_total_allocation_usdt`：你可承受损失范围内（先小）
- `tranche_weights`：`[0.4, 0.3, 0.2, 0.1]`
- `add_step_atr`：`1.2`
- `trail_atr_mult`：`2.5`
- `cooldown_hours`：`3`
- `min_ema_spread_pct`：`0.15%~0.30%` 之间试（过滤震荡很关键）
