"""Standalone macro regime classifier (vendored from Cemini trading_playbook)."""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from typing import Optional

import pandas as pd

from xsp_killer.data_hazards import classify_regime_hazard

logger = logging.getLogger("xsp_killer.macro_regime")

EMA_FAST = 21
SMA_SLOW = 50
EMA_RISING_BARS = 3
LOOKBACK_PERIOD = "3mo"
FETCH_TIMEOUT = 10


@dataclass
class RegimeState:
    regime: str
    spy_price: float
    ema21: float
    sma50: float
    yellow_frac: float | None
    jnk_tlt_flag: bool
    confidence: float
    timestamp: float
    reason: str
    data_hazard: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _fetch_close(ticker: str, period: str = LOOKBACK_PERIOD) -> Optional[pd.Series]:
    try:
        import yfinance as yf

        df = yf.Ticker(ticker).history(period=period, timeout=FETCH_TIMEOUT)
        if df.empty:
            return None
        return df["Close"].dropna()
    except Exception as exc:
        logger.warning("yfinance fetch failed for %s: %s", ticker, exc)
        return None


def _ema(series: pd.Series, span: int) -> float:
    return float(series.ewm(span=span, adjust=False).mean().iloc[-1])


def _sma(series: pd.Series, window: int) -> float:
    return float(series.rolling(window=window).mean().iloc[-1])


def _ema_rising(series: pd.Series, span: int, lookback: int = EMA_RISING_BARS) -> bool:
    ema_vals = series.ewm(span=span, adjust=False).mean()
    return float(ema_vals.iloc[-1]) > float(ema_vals.iloc[-lookback])


def _jnk_tlt_divergence(jnk: pd.Series, tlt: pd.Series, lookback: int = 5) -> bool:
    if len(jnk) < lookback + 1 or len(tlt) < lookback + 1:
        return False
    jnk_ret = (float(jnk.iloc[-1]) - float(jnk.iloc[-lookback])) / float(
        jnk.iloc[-lookback]
    )
    tlt_ret = (float(tlt.iloc[-1]) - float(tlt.iloc[-lookback])) / float(
        tlt.iloc[-lookback]
    )
    return jnk_ret < tlt_ret


def yellow_band_frac(spy_price: float, ema21: float, sma50: float) -> float | None:
    """Return normalized position inside the YELLOW band, else None."""
    if not (sma50 < spy_price <= ema21):
        return None
    span = ema21 - sma50
    if span <= 0:
        return 0.5
    return max(0.0, min(1.0, (spy_price - sma50) / span))


def _classify_with_distance(
    spy_price: float, ema21_val: float, sma50_val: float, ema21_up: bool
) -> tuple[str, float, str]:
    if spy_price > ema21_val and ema21_up:
        regime = "GREEN"
        dist = (spy_price - ema21_val) / ema21_val
        confidence = round(0.65 + 0.30 * min(1.0, dist / 0.03), 4)
        reason = f"SPY {spy_price:.2f} > EMA21 {ema21_val:.2f} (rising)"
    elif spy_price > sma50_val:
        regime = "YELLOW"
        frac = yellow_band_frac(spy_price, ema21_val, sma50_val)
        if frac is None:
            frac = 0.5
        confidence = round(0.55 + 0.20 * max(0.0, min(1.0, frac)), 4)
        reason = (
            f"SPY {spy_price:.2f} < EMA21 {ema21_val:.2f} but > SMA50 {sma50_val:.2f}"
        )
    else:
        regime = "RED"
        dist = (sma50_val - spy_price) / sma50_val
        confidence = round(0.65 + 0.25 * min(1.0, dist / 0.03), 4)
        reason = f"SPY {spy_price:.2f} < SMA50 {sma50_val:.2f}"
    return regime, confidence, reason


def classify_regime() -> RegimeState:
    """Classify macro regime; defaults RED on data failure."""
    spy = _fetch_close("SPY")
    jnk = _fetch_close("JNK")
    tlt = _fetch_close("TLT")

    if spy is None or len(spy) < SMA_SLOW:
        reason = "Insufficient SPY data — defensive default"
        return RegimeState(
            regime="RED",
            spy_price=0.0,
            ema21=0.0,
            sma50=0.0,
            yellow_frac=None,
            jnk_tlt_flag=False,
            confidence=0.1,
            timestamp=time.time(),
            reason=reason,
            data_hazard=classify_regime_hazard(reason),
        )

    spy_price = float(spy.iloc[-1])
    ema21_val = _ema(spy, EMA_FAST)
    sma50_val = _sma(spy, SMA_SLOW)
    ema21_up = _ema_rising(spy, EMA_FAST)

    jnk_tlt_flag = False
    if jnk is not None and tlt is not None and spy_price > ema21_val:
        jnk_tlt_flag = _jnk_tlt_divergence(jnk, tlt)

    regime, confidence, reason = _classify_with_distance(
        spy_price, ema21_val, sma50_val, ema21_up
    )
    if jnk_tlt_flag:
        confidence = round(max(0.45, confidence - 0.15), 4)
        reason += " | WARN: JNK underperforming TLT — failed breakout risk"

    yellow_frac = yellow_band_frac(spy_price, ema21_val, sma50_val)

    return RegimeState(
        regime=regime,
        spy_price=round(spy_price, 4),
        ema21=round(ema21_val, 4),
        sma50=round(sma50_val, 4),
        yellow_frac=(round(yellow_frac, 4) if yellow_frac is not None else None),
        jnk_tlt_flag=jnk_tlt_flag,
        confidence=confidence,
        timestamp=time.time(),
        reason=reason,
    )
