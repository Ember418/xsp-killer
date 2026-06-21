"""Paper economics slippage model."""

from xsp_killer.paper_economics import PaperEconomics, entry_fill_premium


def test_slippage_capped_for_expensive_premium():
    econ = PaperEconomics(
        commission_usd_per_contract=0.65,
        slippage_pct_of_premium=0.005,
        slippage_usd_per_share=0.12,
        slippage_max_pct_of_premium=0.015,
    )
    fill = entry_fill_premium(61.0, econ)
    slip = fill - 61.0 - econ.commission_usd_per_contract / 100.0
    assert slip <= 61.0 * 0.015 + 0.001
    assert slip >= 0.12
