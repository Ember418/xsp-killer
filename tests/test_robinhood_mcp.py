"""Tests for Robinhood Agentic MCP adapter (mocked — no live RH)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from xsp_killer.rh_broker import fetch_robinhood_option_positions, rh_read_enabled
from xsp_killer.robinhood_mcp import (
    RhMcpConfig,
    RhMcpLiveExitsDisabled,
    RhMcpNotReady,
    RobinhoodMCPAdapter,
    live_exits_enabled,
    normalize_mcp_position,
    rh_mcp_enabled,
)


def test_rh_mcp_disabled_by_default(monkeypatch):
    monkeypatch.delenv("XSP_LANE_A_RH_MCP", raising=False)
    assert rh_mcp_enabled() is False
    assert rh_read_enabled() is False


def test_live_exits_disabled_by_default(monkeypatch):
    monkeypatch.delenv("XSP_LANE_A_LIVE_EXITS", raising=False)
    monkeypatch.delenv("RH_AGENTIC_ACCOUNT_ID", raising=False)
    cfg = RhMcpConfig(agentic_account_id="", live_exits=False)
    assert live_exits_enabled(config=cfg) is False


def test_live_exits_requires_agentic_account(monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_LIVE_EXITS", "true")
    monkeypatch.delenv("RH_AGENTIC_ACCOUNT_ID", raising=False)
    cfg = RhMcpConfig(agentic_account_id="", live_exits=False)
    assert live_exits_enabled(config=cfg) is False


def test_fetch_mcp_not_ready_without_token(monkeypatch, tmp_path):
    monkeypatch.setenv("XSP_LANE_A_RH_MCP", "true")
    token = tmp_path / "token.json"
    cfg = RhMcpConfig(token_path=token)
    monkeypatch.setattr(
        "xsp_killer.robinhood_mcp.RhMcpConfig.load", lambda path=None: cfg
    )
    rows, err = fetch_robinhood_option_positions()
    assert rows == []
    assert err and "token missing" in err


def test_normalize_mcp_position():
    row = normalize_mcp_position(
        {
            "underlying_symbol": "XSP",
            "type": "call",
            "strike": 7500,
            "expiration": "2026-07-18",
            "qty": 1,
            "mark": 6.5,
            "instrument_id": "abc123",
        }
    )
    assert row["chain_symbol"] == "XSP"
    assert row["type"] == "call"
    assert row["strike_price"] == 7500
    assert row["_source"] == "rh_mcp"


def test_adapter_get_positions_mocked(tmp_path):
    token = tmp_path / "token.json"
    token.write_text(json.dumps({"access_token": "test-token"}), encoding="utf-8")
    audit = tmp_path / "audit.jsonl"
    cfg = RhMcpConfig(
        token_path=token,
        audit_log=audit,
        agentic_account_id="agentic-1",
    )

    def fake_http(url, body, headers):
        assert headers["Authorization"] == "Bearer test-token"
        return {
            "result": {
                "structuredContent": [
                    {
                        "chain_symbol": "XSP",
                        "type": "call",
                        "strike_price": 7500,
                        "expiration_date": "2026-07-18",
                        "quantity": 2,
                        "mark_price": 5.0,
                    }
                ]
            }
        }

    adapter = RobinhoodMCPAdapter(config=cfg, http_post=fake_http)
    rows = adapter.get_open_option_positions()
    assert len(rows) == 1
    assert rows[0]["chain_symbol"] == "XSP"
    assert audit.is_file()
    assert "get_option_positions" in audit.read_text(encoding="utf-8")


def test_place_order_blocked_when_live_exits_off(tmp_path):
    token = tmp_path / "token.json"
    token.write_text(json.dumps({"access_token": "t"}), encoding="utf-8")
    cfg = RhMcpConfig(token_path=token, agentic_account_id="agentic-1", live_exits=False)

    def fake_http(url, body, headers):
        return {"result": {"structuredContent": {"ok": True}}}

    adapter = RobinhoodMCPAdapter(config=cfg, http_post=fake_http)
    with pytest.raises(RhMcpLiveExitsDisabled):
        adapter.place_option_order({"quantity": 1, "side": "sell"})


def test_rh_mcp_config_loads_yaml(tmp_path):
    yaml_path = tmp_path / "rh_mcp.yaml"
    yaml_path.write_text(
        "agentic_account_id: 'acct-99'\nmax_contracts_per_order: 2\n",
        encoding="utf-8",
    )
    cfg = RhMcpConfig.load(yaml_path)
    assert cfg.agentic_account_id == "acct-99"
    assert cfg.max_contracts_per_order == 2
