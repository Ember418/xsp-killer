"""Tests for Robinhood Agentic MCP adapter (mocked — no live RH)."""

from __future__ import annotations

import json

import pytest

from xsp_killer.rh_broker import fetch_robinhood_option_positions, rh_read_enabled
from xsp_killer.robinhood_mcp import (
    RhMcpConfig,
    RhMcpError,
    RhMcpLiveExitsDisabled,
    RobinhoodMCPAdapter,
    live_exits_enabled,
    normalize_mcp_position,
    parse_mcp_http_response,
    rh_mcp_enabled,
)


def test_rh_b_poll_separate_from_lane_a(monkeypatch):
    monkeypatch.delenv("XSP_LANE_A_RH_POLL", raising=False)
    monkeypatch.delenv("XSP_LANE_B_RH_POLL", raising=False)
    monkeypatch.delenv("XSP_LANE_A_RH_MCP", raising=False)

    from xsp_killer.rh_broker import rh_poll_enabled, rh_read_enabled

    assert rh_poll_enabled(lane="a") is False
    assert rh_poll_enabled(lane="b") is False
    assert rh_read_enabled(lane="b") is False

    monkeypatch.setenv("XSP_LANE_A_RH_POLL", "true")
    assert rh_poll_enabled(lane="a") is True
    assert rh_poll_enabled(lane="b") is True  # back-compat fallback

    monkeypatch.setenv("XSP_LANE_A_RH_POLL", "false")
    monkeypatch.setenv("XSP_LANE_B_RH_POLL", "true")
    assert rh_poll_enabled(lane="a") is False
    assert rh_poll_enabled(lane="b") is True


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


def test_parse_mcp_http_response_sse():
    body = (
        "event: message\n"
        'data: {"jsonrpc":"2.0","id":1,'
        '"result":{"content":[{"type":"text","text":"{}"}]}}\n'
    )
    parsed = parse_mcp_http_response(body)
    assert parsed["id"] == 1


def test_get_option_chains_uses_underlying_symbol(tmp_path):
    token = tmp_path / "token.json"
    token.write_text(json.dumps({"access_token": "t"}), encoding="utf-8")
    cfg = RhMcpConfig(token_path=token, audit_log=tmp_path / "audit.jsonl")
    seen: dict[str, object] = {}

    def fake_http(url, body, headers):
        payload = json.loads(body.decode("utf-8"))
        seen.update(payload["params"]["arguments"])
        return {
            "result": {
                "structuredContent": {
                    "data": {
                        "chains": [
                            {
                                "id": "chain-1",
                                "symbol": "XSP",
                                "can_open_position": True,
                                "expiration_dates": ["2026-07-18"],
                            }
                        ]
                    }
                }
            }
        }

    adapter = RobinhoodMCPAdapter(config=cfg, http_post=fake_http)
    chain = adapter.get_option_chains("xsp")
    assert seen == {"underlying_symbol": "XSP"}
    assert "chain_symbol" not in seen
    assert chain["symbol"] == "XSP"
    assert chain["expiration_dates"] == ["2026-07-18"]


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


def test_place_order_blocked_when_live_exits_off(tmp_path, monkeypatch):
    monkeypatch.delenv("RH_AGENTIC_ACCOUNT_ID", raising=False)
    token = tmp_path / "token.json"
    token.write_text(json.dumps({"access_token": "t"}), encoding="utf-8")
    audit = tmp_path / "audit.jsonl"
    cfg = RhMcpConfig(
        token_path=token,
        audit_log=audit,
        agentic_account_id="agentic-1",
        live_exits=False,
    )

    def fake_http(url, body, headers):
        return {"result": {"structuredContent": {"ok": True}}}

    adapter = RobinhoodMCPAdapter(config=cfg, http_post=fake_http)
    with pytest.raises(RhMcpLiveExitsDisabled):
        adapter.place_option_order({"quantity": 1, "side": "sell"})
    audit_rows = [json.loads(line) for line in audit.read_text().splitlines()]
    deny = audit_rows[-1]
    assert deny["event"] == "deny"
    assert deny["invariant"] == "I7"
    assert deny["principal"]["agentic_account_id"] == "agentic-1"


def test_place_order_requires_matching_review_grant(tmp_path, monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_LIVE_EXITS", "true")
    token = tmp_path / "token.json"
    token.write_text(json.dumps({"access_token": "t"}), encoding="utf-8")
    audit = tmp_path / "audit.jsonl"
    cfg = RhMcpConfig(
        token_path=token,
        audit_log=audit,
        agentic_account_id="agentic-1",
        live_exits=True,
        require_review_before_place=True,
    )

    def fake_http(url, body, headers):
        return {"result": {"structuredContent": {"ok": True}}}

    adapter = RobinhoodMCPAdapter(config=cfg, http_post=fake_http)
    with pytest.raises(RhMcpError):
        adapter.place_option_order({"quantity": 1, "side": "sell", "option_id": "x"})
    deny = json.loads(audit.read_text().strip().splitlines()[-1])
    assert deny["invariant"] == "I2"


def test_review_grant_allows_matching_place(tmp_path, monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_LIVE_EXITS", "true")
    token = tmp_path / "token.json"
    token.write_text(json.dumps({"access_token": "t"}), encoding="utf-8")
    cfg = RhMcpConfig(
        token_path=token,
        agentic_account_id="agentic-1",
        live_exits=True,
        require_review_before_place=True,
    )
    order = {"quantity": 1, "side": "sell", "option_id": "opt-1"}

    def fake_http(url, body, headers):
        return {"result": {"structuredContent": {"ok": True}}}

    adapter = RobinhoodMCPAdapter(config=cfg, http_post=fake_http)
    adapter.review_option_order(order)
    result = adapter.place_option_order(dict(order))
    assert result == {"ok": True}


def test_review_grant_allows_matching_place_legs_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_LIVE_EXITS", "true")
    token = tmp_path / "token.json"
    token.write_text(json.dumps({"access_token": "t"}), encoding="utf-8")
    cfg = RhMcpConfig(
        token_path=token,
        agentic_account_id="agentic-1",
        live_exits=True,
        require_review_before_place=True,
    )
    order = {
        "account_number": "agentic-1",
        "legs": [{"option_id": "opt-1", "side": "sell", "position_effect": "close"}],
        "type": "limit",
        "quantity": "1",
        "price": "5.00",
    }

    def fake_http(url, body, headers):
        return {"result": {"structuredContent": {"ok": True}}}

    adapter = RobinhoodMCPAdapter(config=cfg, http_post=fake_http)
    adapter.review_option_order(order)
    result = adapter.place_option_order(dict(order))
    assert result == {"ok": True}


def test_place_order_account_number_pin_rejects_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_LIVE_EXITS", "true")
    token = tmp_path / "token.json"
    token.write_text(json.dumps({"access_token": "t"}), encoding="utf-8")
    audit = tmp_path / "audit.jsonl"
    cfg = RhMcpConfig(
        token_path=token,
        audit_log=audit,
        agentic_account_id="agentic-1",
        live_exits=True,
        require_review_before_place=False,
    )

    def fake_http(url, body, headers):
        return {"result": {"structuredContent": {"ok": True}}}

    adapter = RobinhoodMCPAdapter(config=cfg, http_post=fake_http)
    order = {
        "account_number": "not-agentic",
        "legs": [{"option_id": "opt-1", "side": "sell", "position_effect": "close"}],
        "type": "market",
        "quantity": "1",
    }
    with pytest.raises(Exception):
        adapter.place_option_order(order)
    deny = json.loads(audit.read_text().strip().splitlines()[-1])
    assert deny["invariant"] == "I3"


def test_ratio_quantity_counts_toward_max_contracts(tmp_path, monkeypatch):
    monkeypatch.setenv("XSP_LANE_A_LIVE_EXITS", "true")
    token = tmp_path / "token.json"
    token.write_text(json.dumps({"access_token": "t"}), encoding="utf-8")
    audit = tmp_path / "audit.jsonl"
    cfg = RhMcpConfig(
        token_path=token,
        audit_log=audit,
        agentic_account_id="agentic-1",
        live_exits=True,
        require_review_before_place=False,
        max_contracts_per_order=2,
    )

    def fake_http(url, body, headers):
        return {"result": {"structuredContent": {"ok": True}}}

    adapter = RobinhoodMCPAdapter(config=cfg, http_post=fake_http)
    order = {
        "account_number": "agentic-1",
        "legs": [
            {
                "option_id": "opt-1",
                "side": "sell",
                "position_effect": "close",
                "ratio_quantity": 3,
            }
        ],
        "type": "market",
        "quantity": "1",
    }
    with pytest.raises(RhMcpError):
        adapter.place_option_order(order)
    deny = json.loads(audit.read_text().strip().splitlines()[-1])
    assert deny["invariant"] == "I5"


def test_rh_mcp_config_loads_yaml(tmp_path, monkeypatch):
    monkeypatch.delenv("RH_AGENTIC_ACCOUNT_ID", raising=False)
    yaml_path = tmp_path / "rh_mcp.yaml"
    yaml_path.write_text(
        "agentic_account_id: 'acct-99'\nmax_contracts_per_order: 2\n",
        encoding="utf-8",
    )
    cfg = RhMcpConfig.load(yaml_path)
    assert cfg.agentic_account_id == "acct-99"
    assert cfg.max_contracts_per_order == 2
