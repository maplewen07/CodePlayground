from dataclasses import dataclass
from typing import Tuple


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