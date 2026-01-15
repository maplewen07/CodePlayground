from typing import List


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