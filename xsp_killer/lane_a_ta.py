"""XSP Lane A — Bollinger Band + VWAP signals on SPY (mentor playbook).

Entry: dump touches lower/mid BB then bounces.
Exit: pump touches upper BB then rejects.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, time
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import pandas as pd
import yaml

logger = logging.getLogger("xsp_killer.xsp_lane_a_ta")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES = ROOT / "config" / "lane_a_rules.yaml"
ET = ZoneInfo("America/New_York")

Timeframe = Literal["15m", "1h"]


@dataclass
class TaRules:
    symbol: str
    primary_timeframe: Timeframe
    confirm_timeframe: Timeframe
    bb_period: int
    bb_std: float
    require_vwap_reclaim: bool
    upper_bb_touch_tolerance_pct: float
    suppress_morning_cut_dte_gte: int
    entry_mode: str  # close_window_and_bb | bb_bounce | close_window_only
    intraday_entry_enabled: bool

    @classmethod
    def from_yaml(cls, path: Path) -> TaRules:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        ta = data.get("ta") or {}
        entry_ta = ta.get("entry") or {}
        exit_ta = ta.get("exit") or {}
        hold = ta.get("hold") or {}
        return cls(
            symbol=str(ta.get("symbol", "SPY")),
            primary_timeframe=str(ta.get("primary_timeframe", "1h")),  # type: ignore[arg-type]
            confirm_timeframe=str(ta.get("confirm_timeframe", "15m")),  # type: ignore[arg-type]
            bb_period=int(ta.get("bb_period", 20)),
            bb_std=float(ta.get("bb_std", 2.0)),
            require_vwap_reclaim=bool(entry_ta.get("require_vwap_reclaim", True)),
            upper_bb_touch_tolerance_pct=float(exit_ta.get("upper_bb_touch_tolerance_pct", 0.002)),
            suppress_morning_cut_dte_gte=int(hold.get("suppress_morning_cut_dte_gte", 30)),
            entry_mode=str(entry_ta.get("mode", "close_window_and_bb")),
            intraday_entry_enabled=bool(entry_ta.get("intraday_enabled", True)),
        )


@dataclass
class BarSnapshot:
    timeframe: str
    ts: str
    close: float
    high: float
    low: float
    vwap: float
    bb_lower: float
    bb_mid: float
    bb_upper: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaSignal:
    signal: str  # bb_bounce_entry | upper_bb_exit | none
    primary: BarSnapshot | None
    confirm: BarSnapshot | None
    entry_ok: bool
    exit_ok: bool
    detail: str
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.primary:
            d["primary"] = self.primary.to_dict()
        if self.confirm:
            d["confirm"] = self.confirm.to_dict()
        return d


def _yf_interval(tf: Timeframe) -> str:
    return "15m" if tf == "15m" else "1h"


def fetch_intraday_bars(symbol: str, timeframe: Timeframe, *, period: str = "10d") -> pd.DataFrame | None:
    try:
        import yfinance as yf

        df = yf.Ticker(symbol).history(period=period, interval=_yf_interval(timeframe), timeout=15)
        if df is None or df.empty:
            return None
        df = df.copy()
        df.columns = [str(c).lower() for c in df.columns]
        return df.dropna(subset=["close"])
    except Exception as exc:
        logger.warning("intraday fetch failed %s %s: %s", symbol, timeframe, exc)
        return None


def compute_vwap(df: pd.DataFrame) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    vol = df.get("volume")
    if vol is None or vol.sum() == 0:
        return typical.expanding().mean()
    cum_vol = vol.cumsum()
    cum_pv = (typical * vol).cumsum()
    return cum_pv / cum_vol.replace(0, pd.NA)


def enrich_bars(df: pd.DataFrame, *, period: int, std: float) -> pd.DataFrame:
    out = df.copy()
    out["bb_mid"] = out["close"].rolling(period).mean()
    rolling_std = out["close"].rolling(period).std()
    out["bb_upper"] = out["bb_mid"] + std * rolling_std
    out["bb_lower"] = out["bb_mid"] - std * rolling_std
    out["vwap"] = compute_vwap(out)
    return out.dropna(subset=["bb_mid", "bb_upper", "bb_lower"])


def _bar_snapshot(row: pd.Series, timeframe: str) -> BarSnapshot:
    ts = row.name
    if hasattr(ts, "isoformat"):
        ts_s = ts.isoformat()
    else:
        ts_s = str(ts)
    return BarSnapshot(
        timeframe=timeframe,
        ts=ts_s,
        close=float(row["close"]),
        high=float(row["high"]),
        low=float(row["low"]),
        vwap=float(row["vwap"]),
        bb_lower=float(row["bb_lower"]),
        bb_mid=float(row["bb_mid"]),
        bb_upper=float(row["bb_upper"]),
    )


def detect_bb_bounce_entry(prev: BarSnapshot, curr: BarSnapshot, *, require_vwap: bool) -> tuple[bool, str]:
    """Dump touched lower or mid band; current bar bounced."""
    touched_lower = prev.low <= prev.bb_lower * 1.002
    touched_mid = prev.low <= prev.bb_mid * 1.002 and prev.close < prev.bb_mid
    dump = touched_lower or touched_mid
    if not dump:
        return False, "no dump touch on prior bar"

    bounced_lower = touched_lower and curr.close > prev.bb_lower and curr.close > curr.bb_mid * 0.998
    bounced_mid = touched_mid and curr.close > prev.bb_mid
    bounce = bounced_lower or bounced_mid
    if not bounce:
        return False, "dump without bounce"

    if require_vwap and curr.close < curr.vwap:
        return False, "bounce below VWAP"

    band = "lower" if touched_lower else "mid"
    return True, f"bb_bounce off {band} band (close {curr.close:.2f} > mid {curr.bb_mid:.2f})"


def detect_upper_bb_exit(prev: BarSnapshot, curr: BarSnapshot, *, tolerance_pct: float) -> tuple[bool, str]:
    """Pump reached upper BB then rejected."""
    upper = curr.bb_upper
    touch = curr.high >= upper * (1.0 - tolerance_pct) or prev.high >= prev.bb_upper * (1.0 - tolerance_pct)
    if not touch:
        return False, "no upper BB touch"

    rejected = curr.close < upper or curr.close < curr.open
    if not rejected:
        return False, "upper BB touch without rejection candle"

    return True, f"upper BB rejection (high {curr.high:.2f}, close {curr.close:.2f}, upper {upper:.2f})"


def evaluate_timeframe(df: pd.DataFrame, timeframe: str, rules: TaRules) -> tuple[BarSnapshot | None, BarSnapshot | None]:
    if df is None or len(df) < rules.bb_period + 2:
        return None, None
    enriched = enrich_bars(df, period=rules.bb_period, std=rules.bb_std)
    if len(enriched) < 2:
        return None, None
    prev_row = enriched.iloc[-2]
    curr_row = enriched.iloc[-1]
    return _bar_snapshot(prev_row, timeframe), _bar_snapshot(curr_row, timeframe)


def evaluate_ta_signals(
    rules: TaRules,
    *,
    bars_primary: pd.DataFrame | None = None,
    bars_confirm: pd.DataFrame | None = None,
    symbol: str | None = None,
) -> TaSignal:
    sym = symbol or rules.symbol
    errors: list[str] = []

    if bars_primary is None:
        bars_primary = fetch_intraday_bars(sym, rules.primary_timeframe)
    if bars_confirm is None:
        bars_confirm = fetch_intraday_bars(sym, rules.confirm_timeframe)

    prev_p, curr_p = evaluate_timeframe(bars_primary, rules.primary_timeframe, rules) if bars_primary is not None else (None, None)
    prev_c, curr_c = evaluate_timeframe(bars_confirm, rules.confirm_timeframe, rules) if bars_confirm is not None else (None, None)

    if curr_p is None:
        errors.append("insufficient primary bars")
        return TaSignal("none", None, curr_c, False, False, "no primary TA data", errors)

    entry_p, entry_detail_p = detect_bb_bounce_entry(prev_p, curr_p, require_vwap=rules.require_vwap_reclaim)
    entry_c = True
    entry_detail_c = "confirm skipped"
    if curr_c is not None and prev_c is not None:
        entry_c, entry_detail_c = detect_bb_bounce_entry(prev_c, curr_c, require_vwap=rules.require_vwap_reclaim)

    entry_ok = entry_p and entry_c
    detail_parts = [f"primary: {entry_detail_p}"]
    if curr_c is not None:
        detail_parts.append(f"confirm: {entry_detail_c}")

    exit_p, exit_detail_p = detect_upper_bb_exit(prev_p, curr_p, tolerance_pct=rules.upper_bb_touch_tolerance_pct)
    exit_c = False
    exit_detail_c = "confirm skipped"
    if curr_c is not None and prev_c is not None:
        exit_c, exit_detail_c = detect_upper_bb_exit(prev_c, curr_c, tolerance_pct=rules.upper_bb_touch_tolerance_pct)

    exit_ok = exit_p or exit_c
    exit_detail = f"primary: {exit_detail_p}; confirm: {exit_detail_c}"

    signal = "none"
    if entry_ok:
        signal = "bb_bounce_entry"
    elif exit_ok:
        signal = "upper_bb_exit"

    return TaSignal(
        signal=signal,
        primary=curr_p,
        confirm=curr_c,
        entry_ok=entry_ok,
        exit_ok=exit_ok,
        detail="; ".join(detail_parts) if entry_ok else exit_detail,
    )


def in_rth(now_et: datetime, *, start: time = time(9, 30), end: time = time(16, 0)) -> bool:
    if now_et.weekday() >= 5:
        return False
    t = now_et.time()
    return start <= t < end


def morning_cut_suppressed(dte: int, rules: TaRules) -> bool:
    return dte >= rules.suppress_morning_cut_dte_gte
