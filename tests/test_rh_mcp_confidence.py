"""Tests for MCP confidence wrapper and fusion rules."""

from __future__ import annotations

import json

from xsp_killer.data_hazards import (
    classify_mcp_read_confidence,
    fusion_tier,
    mcp_read_trusted,
    unwrap_tool_result,
    wrap_tool_result,
)
from xsp_killer.robinhood_mcp import (
    RhMcpConfig,
    RobinhoodMCPAdapter,
    fetch_option_positions_via_mcp,
)


def test_wrap_and_unwrap_tool_result():
    wrapped = wrap_tool_result(
        [{"chain_symbol": "XSP"}],
        confidence=0.92,
        signals=["schema_ok"],
        hazard_class="none",
    )
    assert wrapped["confidence"] == 0.92
    assert unwrap_tool_result(wrapped) == [{"chain_symbol": "XSP"}]


def test_fusion_tiers():
    assert fusion_tier(0.9) == "HIGH"
    assert fusion_tier(0.6) == "MEDIUM"
    assert fusion_tier(0.2) == "LOW"
    assert mcp_read_trusted(wrap_tool_result([], confidence=0.9)) is True
    assert mcp_read_trusted(wrap_tool_result([], confidence=0.2)) is False


def test_classify_mcp_read_confidence_positions():
    conf, hazard, signals = classify_mcp_read_confidence(
        [{"chain_symbol": "XSP", "type": "call"}],
        tool="get_option_positions",
    )
    assert conf >= 0.85
    assert hazard == "none"
    assert "schema_ok" in signals

    conf, hazard, _ = classify_mcp_read_confidence([], tool="get_option_positions")
    assert conf == 0.65
    assert hazard == "none"

    conf, hazard, _ = classify_mcp_read_confidence(
        None,
        tool="get_option_positions",
        error="timeout",
    )
    assert conf < 0.35
    assert hazard == "exec_fail"


def test_adapter_read_wraps_confidence(tmp_path):
    token = tmp_path / "token.json"
    token.write_text(json.dumps({"access_token": "test-token"}), encoding="utf-8")
    cfg = RhMcpConfig(
        token_path=token,
        audit_log=tmp_path / "audit.jsonl",
        agentic_account_id="acct-test",
    )

    def fake_http(url, body, headers):
        return {
            "result": {
                "structuredContent": [
                    {
                        "chain_symbol": "XSP",
                        "type": "call",
                        "strike_price": 7500,
                        "expiration_date": "2026-07-18",
                        "quantity": 1,
                        "mark_price": 5.0,
                    }
                ]
            }
        }

    adapter = RobinhoodMCPAdapter(config=cfg, http_post=fake_http)
    wrapped = adapter.call_tool(
        "get_option_positions",
        {"account_number": "acct-test"},
    )
    assert wrapped["confidence"] >= 0.85
    rows = adapter.get_open_option_positions()
    assert len(rows) == 1
    assert adapter.last_read_confidence()["confidence"] >= 0.85


def test_fetch_rejects_low_confidence(monkeypatch, tmp_path):
    monkeypatch.setenv("XSP_LANE_A_RH_MCP", "true")
    token = tmp_path / "token.json"
    token.write_text(json.dumps({"access_token": "t"}), encoding="utf-8")
    cfg = RhMcpConfig(
        token_path=token,
        audit_log=tmp_path / "audit.jsonl",
        agentic_account_id="acct-test",
    )
    monkeypatch.setattr(
        "xsp_killer.robinhood_mcp.RhMcpConfig.load", lambda path=None: cfg
    )

    monkeypatch.setattr(
        "xsp_killer.robinhood_mcp.classify_mcp_read_confidence",
        lambda *args, **kwargs: (0.2, "exec_fail", ["forced_low"]),
    )

    def fake_http(url, body, headers):
        return {"result": {"structuredContent": []}}

    monkeypatch.setattr(
        "xsp_killer.robinhood_mcp.RobinhoodMCPAdapter._default_http_post",
        lambda self, url, body, headers: fake_http(url, body, headers),
    )
    rows, err = fetch_option_positions_via_mcp()
    assert rows == []
    assert err and "confidence LOW" in err
