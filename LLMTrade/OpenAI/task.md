

## 1) 系统分工（强烈建议这样做）
### 程序端（必须做、可验证）
- 拉数据（1h K线）
- 计算指标/特征（EMA、ATR、趋势强度等）
- 执行风控（仓位上限、止损、冷却、滑点/价差保护）
- 下单与订单状态机（下单、查询、撤单、重试）

### 大模型端（更适合做）
- 基于“结构化特征 + 约束”给出：`BUY / SELL / HOLD`
- 给出仓位比例、止损止盈建议、信号失效时间
- 给出“作废条件”（例如波动过大就不追）

> 关键：**模型不直接接触原始杂乱数据，不直接掌控资金**。

---

## 2) 小时级趋势跟随：推荐你用的“特征集”
你每小时给模型传这些（越结构化越好）：

### A. 市场特征（程序算好再给）
- `close_now`
- `ema_fast`（例如 EMA20）
- `ema_slow`（例如 EMA50）
- `ema_spread_pct = (ema_fast-ema_slow)/ema_slow`
- `ema_fast_slope`（过去 6 小时 EMA20 的斜率）
- `atr_pct`（ATR14 / close）
- `ret_24h`, `ret_72h`
- `hh_72h_dist_pct`（距离72h最高价的百分比）
- `drawdown_72h_pct`
- （可选）`adx` 或一个你自定义的趋势强度分数

### B. 账户与约束（必须给）
- 当前 BTC 持仓数量、USDT 余额
- 你允许的最大仓位（比如最多用可用资金的 30% 买）
- 最大单笔比例、最大日亏损、冷却期（例如 3 小时内最多 1 次交易）
- 允许的订单类型（`MARKET` / `LIMIT`），是否支持 OCO（现货常用）

---

## 3) 让模型只输出“严格 JSON”（可直接解析）
建议固定成这样（字段少但够用）：

```json
{
  "action": "BUY|SELL|HOLD",
  "size_pct": 0.0,
  "order_type": "MARKET|LIMIT",
  "limit_price": null,
  "stop_loss_pct": 0.0,
  "take_profit_pct": 0.0,
  "time_to_live_hours": 0,
  "confidence": 0.0,
  "reasons": ["", "", ""],
  "invalid_if": ["", ""]
}
```

说明（适配现货趋势）：
- `size_pct`：这次用“可用 USDT 的比例”买入（卖出则表示卖出当前 BTC 持仓的比例）
- `stop_loss_pct`：以入场价为基准的止损百分比（例如 0.03 = 3%）
- `take_profit_pct`：趋势跟随可以设得更宽，或干脆用“移动止损”而不是固定止盈
- `time_to_live_hours`：信号过期时间（避免模型输出过时信号被你晚点执行）

---

## 4) 一份你可以直接用的 Prompt 模板（小时级、BTC、趋势跟随）
你每小时调用一次，把下面“输入 JSON”替换成真实数据：

**System（规则）**
- 你是保守的趋势跟随交易助手，只交易 BTC 现货。
- 只能输出一段 JSON，禁止输出任何自然语言。
- 不允许频繁交易：只有在趋势明显时才交易；震荡必须 HOLD。
- 必须给出止损（stop_loss_pct），且不能超过我给定的最大止损。
- `size_pct` 不得超过约束上限。
- 若不确定就 HOLD。

**User（数据+约束）**
- 输入数据 JSON：
  - `features`: { …上面那些指标… }
  - `position`: {btc_qty, usdt_free, avg_price}
  - `constraints`: {max_size_pct, max_stop_loss_pct, cooldown_hours, slippage_guard_pct}

**Assistant（输出 JSON）**
- 按 schema 输出。

---

## 5) 下单前的“硬风控闸门”（趋势策略成败关键）
即使模型说 BUY，你也建议程序端这样卡一下：

1. `confidence < 0.60` → 强制 `HOLD`
2. `size_pct > max_size_pct` → 裁剪到上限
3. `stop_loss_pct <= 0 或 stop_loss_pct > max_stop_loss_pct` → 拒单
4. 冷却期：距离上次成交 < `cooldown_hours` → 拒单
5. 若 `atr_pct` 过高（比如 > 4%）→ 不追单，改 LIMIT 或直接 HOLD
6. 只允许交易一个方向：**趋势跟随建议不要反复反手**（卖出后至少等 1–2 根小时线再考虑买回）

---

## 6) 趋势跟随的“执行细节”（现货 BTC）
### 入场（BUY）
- 趋势条件典型是：`EMA20 > EMA50` 且 `EMA20 slope > 0` 且 `ema_spread_pct` 高于阈值  
- 订单：小时级一般 **MARKET** 就够（但加“滑点保护”：若价格偏离预期太多就拒单）

### 出场（SELL）
趋势跟随更建议：
- **移动止损**（trailing stop）而不是小止盈  
  - 例如：止损价 = 近期最高价 - k * ATR（k=2~3），随新高上移
- 或者简单点：当 `EMA20 < EMA50` 或 `EMA20 slope < 0` 时减仓/清仓

> 现货没有爆仓，但同样要防“趋势结束的大回撤”。

---

## 7) 你最该先做的验证方式（别一上来真钱自动下单）
先跑 **影子模式 2–4 周**：  
每小时让模型输出一次 JSON，但不下单，只记录“如果按它做会怎样”，把手续费/滑点也模拟进去。  
如果影子模式都不稳定，直接实盘通常更糟。
