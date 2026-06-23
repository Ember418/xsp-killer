"""SPY option chain proxy quotes for XSP paper marks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from xsp_killer.paper_economics import SPY_TO_XSP_PREMIUM_SCALE


@dataclass
class SpyCallQuote:
    """Quote row for an XSP strike mapped onto the SPY chain."""

    mid_spy: float | None
    bid_spy: float | None
    ask_spy: float | None
    last_spy: float | None
    spy_row_strike: float | None
    exit_mark_spy: float | None
    mark_xsp: float | None
    exit_mark_xsp: float | None
    stale: bool = False
    stale_reason: str | None = None


def _select_spy_call_row(calls: Any, strike_spy: float) -> Any:
    """Nearest SPY chain row; tie-break toward higher strike at .5 halves (OTM call)."""
    strikes = calls["strike"].astype(float)
    abs_diff = (strikes - strike_spy).abs()
    min_diff = float(abs_diff.min())
    candidates = calls.loc[abs_diff <= min_diff + 1e-9]
    if len(candidates) > 1:
        idx = candidates["strike"].astype(float).idxmax()
        return calls.loc[idx]
    return calls.loc[abs_diff.idxmin()]


def xsp_strike_to_spy_chain_strike(xsp_strike: float) -> float:
    return xsp_strike / 10.0


def _pos_float(val: Any) -> float | None:
    import pandas as pd

    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _conservative_exit_mark_spy(
    *,
    bid: float | None,
    ask: float | None,
    last: float | None,
    mid: float | None,
) -> float | None:
    """Sell-side mark: prefer bid; avoid inflated mids on wide spreads."""
    if bid is not None and ask is not None and ask > 0:
        spread_pct = (ask - bid) / ask
        if spread_pct > 0.15:
            return bid
        if bid is not None:
            return bid
    if bid is not None:
        return bid
    if last is not None:
        return last
    return mid


def fetch_spy_call_quote(
    strike_spy: float,
    expiration: date,
    *,
    entry_mid_xsp: float | None = None,
    last_mark_xsp: float | None = None,
    max_jump_pct: float = 0.22,
) -> SpyCallQuote:
    """Fetch SPY chain quote with conservative exit mark and sanity guards."""
    try:

        from xsp_killer.chain_cache import get_spy_option_chain

        chain = get_spy_option_chain(expiration)
        calls = chain.calls
        if calls is None or calls.empty:
            return SpyCallQuote(None, None, None, None, None, None, None, None, True, "empty_chain")

        row = _select_spy_call_row(calls, strike_spy)
        spy_row = float(row["strike"])
        bid = _pos_float(row.get("bid"))
        ask = _pos_float(row.get("ask"))
        last = _pos_float(row.get("lastPrice"))
        mid = None
        if bid is not None and ask is not None:
            mid = (bid + ask) / 2.0
        elif last is not None:
            mid = last
        elif ask is not None:
            mid = ask
        elif bid is not None:
            mid = bid

        exit_spy = _conservative_exit_mark_spy(bid=bid, ask=ask, last=last, mid=mid)
        mark_xsp = round(mid * SPY_TO_XSP_PREMIUM_SCALE, 4) if mid is not None else None
        exit_xsp = (
            round(exit_spy * SPY_TO_XSP_PREMIUM_SCALE, 4) if exit_spy is not None else None
        )

        stale = False
        reason: str | None = None
        if exit_xsp is not None and entry_mid_xsp is not None and entry_mid_xsp > 0:
            ret = (exit_xsp - entry_mid_xsp) / entry_mid_xsp
            if ret > 0.35:
                stale = True
                reason = f"exit_mark_implied_gain_{ret * 100:.1f}pct_on_red_day_guard"
                exit_xsp = min(exit_xsp, entry_mid_xsp * 1.05)
            elif ret < -0.45:
                stale = True
                reason = f"exit_mark_implied_loss_{ret * 100:.1f}pct_exceeds_sanity"
                exit_xsp = max(exit_xsp, entry_mid_xsp * 0.55)

        if (
            not stale
            and exit_xsp is not None
            and last_mark_xsp is not None
            and last_mark_xsp > 0
        ):
            jump = abs(exit_xsp - last_mark_xsp) / last_mark_xsp
            if jump > max_jump_pct:
                stale = True
                reason = f"mark_jump_{jump * 100:.1f}pct_vs_last_poll"
                exit_xsp = last_mark_xsp

        return SpyCallQuote(
            mid_spy=mid,
            bid_spy=bid,
            ask_spy=ask,
            last_spy=last,
            spy_row_strike=spy_row,
            exit_mark_spy=exit_spy,
            mark_xsp=mark_xsp,
            exit_mark_xsp=exit_xsp,
            stale=stale,
            stale_reason=reason,
        )
    except Exception as exc:
        return SpyCallQuote(None, None, None, None, None, None, None, None, True, str(exc))


def fetch_spy_call_quote_legacy(strike_spy: float, expiration: date) -> tuple[float | None, float | None]:
    """Backward-compatible (mid, delta) for entry paths."""
    q = fetch_spy_call_quote(strike_spy, expiration)
    return q.mid_spy, None
