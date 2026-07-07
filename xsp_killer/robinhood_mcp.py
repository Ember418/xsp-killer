"""Robinhood Agentic Trading MCP adapter — read path + gated writes (Phase 0+).

Headless bridge for systemd cron. Disabled by default; no network calls unless
``XSP_LANE_A_RH_MCP=true`` and a token file exists.

See ``docs/rh_mcp_runbook.md`` and ``config/rh_mcp.yaml``.

Invariants:
- Disabled by default (``XSP_LANE_A_RH_MCP`` false); no MCP network unless
  env + token file.
- Write path enforces HCP I2 (review→place grant chain) and I7 (deny-path
  audit on blocks).
- LOW-confidence MCP reads (``mcp_read_trusted``) must not drive
  position/monitor decisions.
- No live exits without operator GO: ``place_option_order`` requires
  ``XSP_LANE_A_LIVE_EXITS`` + pinned account.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from xsp_killer.data_hazards import (
    classify_mcp_read_confidence,
    fusion_tier,
    mcp_read_trusted,
    unwrap_tool_result,
    wrap_tool_result,
)

logger = logging.getLogger("xsp_killer.robinhood_mcp")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "rh_mcp.yaml"
_last_mcp_fetch_wrap: dict[str, Any] | None = None
MCP_JSONRPC_VERSION = "2.0"
MCP_ACCEPT = "application/json, text/event-stream"


def parse_mcp_http_response(raw: str) -> dict[str, Any]:
    """Parse Streamable HTTP MCP body (JSON or SSE ``event: message`` frames)."""
    text = raw.strip()
    if not text:
        raise RhMcpError("rh_mcp empty response")
    if text.startswith("{"):
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise RhMcpError("rh_mcp expected JSON object response")
        return parsed
    if text.startswith("event:") or "\ndata:" in text:
        for line in text.splitlines():
            if line.startswith("data:"):
                payload = line[5:].strip()
                if not payload:
                    continue
                parsed = json.loads(payload)
                if isinstance(parsed, dict):
                    return parsed
        raise RhMcpError("rh_mcp SSE response missing data frame")
    raise RhMcpError(f"rh_mcp non-JSON response: {text[:200]}")

READ_TOOLS = frozenset(
    {
        "get_accounts",
        "get_portfolio",
        "get_option_positions",
        "get_option_orders",
        "get_option_chains",
        "get_option_instruments",
        "get_option_quotes",
        "get_equity_historicals",
        "get_indexes",
        "get_index_quotes",
        "search",
    }
)
WRITE_TOOLS = frozenset(
    {
        "review_option_order",
        "place_option_order",
        "cancel_option_order",
    }
)
ALLOWED_TOOLS = READ_TOOLS | WRITE_TOOLS


class RhMcpError(Exception):
    """Base MCP adapter error."""


class RhMcpNotReady(RhMcpError):
    """MCP enabled but token/config missing."""


class RhMcpLiveExitsDisabled(RhMcpError):
    """place_option_order blocked by kill switch."""


class RhMcpAccountRejected(RhMcpError):
    """Order target account is not the pinned Agentic account."""


def rh_mcp_enabled() -> bool:
    return os.getenv("XSP_LANE_A_RH_MCP", "false").strip().lower() in (
        "1",
        "true",
        "yes",
    )


@dataclass
class RhMcpConfig:
    agentic_account_id: str = ""
    mcp_url: str = "https://agent.robinhood.com/mcp/trading"
    token_path: Path = field(
        default_factory=lambda: ROOT / ".local/robinhood_mcp_token.json"
    )
    allowed_chain_symbols: tuple[str, ...] = ("XSP", "SPX")
    live_exits: bool = False
    max_contracts_per_order: int = 1
    require_review_before_place: bool = True
    audit_log: Path = field(default_factory=lambda: ROOT / "logs/rh_mcp_audit.jsonl")

    @classmethod
    def load(cls, path: Path | None = None) -> RhMcpConfig:
        import yaml

        cfg_path = path or DEFAULT_CONFIG
        data: dict[str, Any] = {}
        if cfg_path.is_file():
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        token_raw = str(data.get("token_path") or ".local/robinhood_mcp_token.json")
        audit_raw = str(data.get("audit_log") or "logs/rh_mcp_audit.jsonl")
        symbols = data.get("allowed_chain_symbols") or ["XSP", "SPX"]
        account = os.getenv("RH_AGENTIC_ACCOUNT_ID", "").strip() or str(
            data.get("agentic_account_id") or ""
        )
        return cls(
            agentic_account_id=account,
            mcp_url=str(data.get("mcp_url") or cls.mcp_url),
            token_path=(ROOT / token_raw).resolve()
            if not Path(token_raw).is_absolute()
            else Path(token_raw),
            allowed_chain_symbols=tuple(str(s).upper() for s in symbols),
            live_exits=bool(data.get("live_exits", False)),
            max_contracts_per_order=int(data.get("max_contracts_per_order") or 1),
            require_review_before_place=bool(
                data.get("require_review_before_place", True)
            ),
            audit_log=(ROOT / audit_raw).resolve()
            if not Path(audit_raw).is_absolute()
            else Path(audit_raw),
        )


def live_exits_enabled(*, config: RhMcpConfig | None = None) -> bool:
    env = os.getenv("XSP_LANE_A_LIVE_EXITS", "").strip().lower()
    if env in ("1", "true", "yes"):
        flag = True
    elif env in ("0", "false", "no"):
        flag = False
    else:
        cfg = config or RhMcpConfig.load()
        flag = cfg.live_exits
    if not flag:
        return False
    cfg = config or RhMcpConfig.load()
    account = os.getenv("RH_AGENTIC_ACCOUNT_ID", "").strip() or cfg.agentic_account_id
    return bool(account)


def _load_token(token_path: Path) -> dict[str, Any]:
    if not token_path.is_file():
        raise RhMcpNotReady(
            f"rh_mcp: token missing at {token_path} — complete desktop OAuth first "
            "(see docs/rh_mcp_runbook.md)"
        )
    try:
        data = json.loads(token_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RhMcpNotReady(
            f"rh_mcp: invalid token JSON at {token_path}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise RhMcpNotReady(f"rh_mcp: token file must be a JSON object: {token_path}")
    return data


def _extract_bearer(token: dict[str, Any]) -> str:
    for key in ("access_token", "token", "bearer"):
        val = token.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    raise RhMcpNotReady(
        "rh_mcp: token file missing access_token — re-export from desktop OAuth session"
    )


def normalize_mcp_position(row: dict[str, Any]) -> dict[str, Any]:
    """Map MCP position payload toward robin_stocks-shaped dicts for monitors."""
    chain = str(
        row.get("chain_symbol")
        or row.get("symbol")
        or row.get("underlying_symbol")
        or ""
    ).upper()
    option_type = str(row.get("type") or row.get("option_type") or "").lower()
    if option_type in ("call", "put"):
        pass
    elif row.get("direction") in ("long", "short"):
        option_type = str(row.get("option_type") or row.get("type") or "").lower()
    strike = row.get("strike_price") or row.get("strike")
    exp = row.get("expiration_date") or row.get("expiration")
    qty = row.get("quantity") or row.get("qty") or row.get("contracts")
    avg = (
        row.get("average_price") or row.get("average_open_price") or row.get("avg_cost")
    )
    mark = row.get("mark_price") or row.get("adjusted_mark_price") or row.get("mark")
    oid = row.get("option_id") or row.get("id") or row.get("instrument_id")
    out = dict(row)
    out.update(
        {
            "chain_symbol": chain,
            "type": option_type,
            "strike_price": strike,
            "expiration_date": exp,
            "quantity": qty,
            "average_price": avg,
            "mark_price": mark,
            "option_id": oid,
            "_source": "rh_mcp",
        }
    )
    return out


def _review_grant_key(order: dict[str, Any]) -> str:
    keys = ("side", "quantity", "option_id", "chain_symbol", "strike_price", "type")
    payload = {key: order.get(key) for key in keys if order.get(key) is not None}
    return json.dumps(payload, sort_keys=True, default=str)


def _session_principal(
    token_data: dict[str, Any] | None,
    *,
    config: RhMcpConfig,
) -> dict[str, Any]:
    account = (
        os.getenv("RH_AGENTIC_ACCOUNT_ID", "").strip() or config.agentic_account_id
    )
    subject = None
    if isinstance(token_data, dict):
        subject = token_data.get("sub") or token_data.get("user_id")
    return {
        "agentic_account_id": account or None,
        "token_subject": subject,
    }


class RobinhoodMCPAdapter:
    """HTTP MCP client with tool allowlist, audit log, and write gates."""

    def __init__(
        self,
        config: RhMcpConfig | None = None,
        *,
        http_post: Callable[..., Any] | None = None,
    ) -> None:
        self.config = config or RhMcpConfig.load()
        self._http_post = http_post or self._default_http_post
        self._last_review: dict[str, Any] | None = None
        self._active_grant: dict[str, Any] | None = None
        self.last_read_wrap: dict[str, Any] | None = None
        self._principal: dict[str, Any] = _session_principal(None, config=self.config)

    def _default_http_post(
        self, url: str, body: bytes, headers: dict[str, str]
    ) -> dict[str, Any]:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RhMcpError(f"rh_mcp HTTP {exc.code}: {detail[:500]}") from exc
        except urllib.error.URLError as exc:
            raise RhMcpError(f"rh_mcp network error: {exc}") from exc
        return parse_mcp_http_response(raw)

    def _audit(
        self,
        tool: str,
        arguments: dict[str, Any],
        *,
        ok: bool,
        result: Any = None,
        error: str | None = None,
        event: str = "allow",
        invariant: str | None = None,
    ) -> None:
        path = self.config.audit_log
        path.parent.mkdir(parents=True, exist_ok=True)
        row: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "tool": tool,
            "ok": ok,
            "arguments": arguments,
            "principal": self._principal,
        }
        if invariant:
            row["invariant"] = invariant
        if error:
            row["error"] = error
        if ok and tool in READ_TOOLS:
            if isinstance(result, list):
                row["result_count"] = len(result)
            elif isinstance(result, dict):
                row["result_keys"] = sorted(result.keys())[:20]
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")

    def _audit_deny(
        self,
        tool: str,
        arguments: dict[str, Any],
        *,
        reason: str,
        invariant: str,
    ) -> None:
        """HCP I7 — deny-path audit with principal + capability + reason."""
        self._audit(
            tool,
            arguments,
            ok=False,
            error=reason,
            event="deny",
            invariant=invariant,
        )

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        if name not in ALLOWED_TOOLS:
            self._audit_deny(
                name,
                arguments or {},
                reason=f"rh_mcp tool not allowlisted: {name}",
                invariant="I5",
            )
            raise RhMcpError(f"rh_mcp tool not allowlisted: {name}")
        args = arguments or {}
        if name in WRITE_TOOLS:
            self._enforce_write_gates(name, args)
        token_data = _load_token(self.config.token_path)
        self._principal = _session_principal(token_data, config=self.config)
        bearer = _extract_bearer(token_data)
        payload = {
            "jsonrpc": MCP_JSONRPC_VERSION,
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {bearer}",
        }
        try:
            response = self._http_post(
                self.config.mcp_url,
                json.dumps(payload).encode("utf-8"),
                headers,
            )
            result = self._unwrap_tool_result(response)
            if name in READ_TOOLS:
                confidence, hazard_class, signals = classify_mcp_read_confidence(
                    result,
                    tool=name,
                )
                wrapped = wrap_tool_result(
                    result,
                    confidence=confidence,
                    signals=signals,
                    hazard_class=hazard_class,
                )
                self.last_read_wrap = wrapped
                self._audit(name, args, ok=True, result=result)
                return wrapped
            self._audit(name, args, ok=True, result=result)
            if name == "review_option_order":
                self._last_review = {"arguments": args, "result": result}
                self._active_grant = {
                    "grant_id": secrets.token_hex(8),
                    "order_key": _review_grant_key(args),
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
            if name == "place_option_order":
                self._active_grant = None
            return result
        except Exception as exc:
            self._audit(name, args, ok=False, error=str(exc))
            raise

    @staticmethod
    def _unwrap_tool_result(response: dict[str, Any]) -> Any:
        if "error" in response:
            err = response["error"]
            if isinstance(err, dict):
                raise RhMcpError(
                    f"rh_mcp tool error: {err.get('message') or err.get('code') or err}"
                )
            raise RhMcpError(f"rh_mcp tool error: {err}")
        result = response.get("result")
        if isinstance(result, dict):
            content = result.get("content")
            if isinstance(content, list):
                texts = [
                    c.get("text")
                    for c in content
                    if isinstance(c, dict) and c.get("type") == "text"
                ]
                if len(texts) == 1:
                    try:
                        return json.loads(texts[0])
                    except (json.JSONDecodeError, TypeError):
                        return texts[0]
            structured = result.get("structuredContent")
            if structured is not None:
                return structured
        return result

    def _enforce_write_gates(self, name: str, args: dict[str, Any]) -> None:
        if name == "place_option_order":
            if not live_exits_enabled(config=self.config):
                self._audit_deny(
                    name,
                    args,
                    reason=(
                        "rh_mcp: place_option_order blocked — "
                        "set XSP_LANE_A_LIVE_EXITS=true "
                        "and RH_AGENTIC_ACCOUNT_ID after operator GO"
                    ),
                    invariant="I7",
                )
                raise RhMcpLiveExitsDisabled(
                    "rh_mcp: place_option_order blocked — "
                    "set XSP_LANE_A_LIVE_EXITS=true "
                    "and RH_AGENTIC_ACCOUNT_ID after operator GO"
                )
            qty = args.get("quantity") or args.get("contracts") or 1
            try:
                qty_n = float(qty)
            except (TypeError, ValueError):
                qty_n = 1.0
            if qty_n > self.config.max_contracts_per_order:
                reason = (
                    f"rh_mcp: quantity {qty_n} exceeds max_contracts_per_order "
                    f"{self.config.max_contracts_per_order}"
                )
                self._audit_deny(name, args, reason=reason, invariant="I5")
                raise RhMcpError(reason)
            account = str(args.get("account_id") or args.get("account") or "")
            pinned = self.config.agentic_account_id
            if pinned and account and account != pinned:
                reason = (
                    f"rh_mcp: order account {account!r} != pinned Agentic {pinned!r}"
                )
                self._audit_deny(name, args, reason=reason, invariant="I3")
                raise RhMcpAccountRejected(reason)
            if self.config.require_review_before_place:
                grant_key = _review_grant_key(args)
                if self._active_grant is None:
                    self._audit_deny(
                        name,
                        args,
                        reason=(
                            "rh_mcp: place_option_order requires "
                            "prior review_option_order"
                        ),
                        invariant="I2",
                    )
                    raise RhMcpError(
                        "rh_mcp: place_option_order requires prior review_option_order"
                    )
                if self._active_grant.get("order_key") != grant_key:
                    self._audit_deny(
                        name,
                        args,
                        reason="rh_mcp: place_option_order grant does not match review",
                        invariant="I2",
                    )
                    raise RhMcpError(
                        "rh_mcp: place_option_order grant does not match review"
                    )

    def get_accounts(self) -> list[dict[str, Any]]:
        wrapped = self.call_tool("get_accounts", {})
        raw = unwrap_tool_result(wrapped)
        if isinstance(raw, dict):
            accounts = raw.get("accounts") or raw.get("data", {}).get("accounts")
            if isinstance(accounts, list):
                return [a for a in accounts if isinstance(a, dict)]
        if isinstance(raw, list):
            return [a for a in raw if isinstance(a, dict)]
        return []

    def resolve_account_number(self) -> str:
        pinned = (
            os.getenv("RH_AGENTIC_ACCOUNT_ID", "").strip()
            or self.config.agentic_account_id
        )
        if pinned:
            return pinned
        accounts = self.get_accounts()
        for acct in accounts:
            nickname = str(acct.get("nickname") or "").lower()
            label = str(
                acct.get("brokerage_account_type")
                or acct.get("account_type")
                or acct.get("type")
                or ""
            ).lower()
            if "agentic" in nickname or "agentic" in label:
                num = acct.get("account_number") or acct.get("rhs_account_number")
                if num:
                    return str(num)
        if len(accounts) == 1:
            num = accounts[0].get("account_number") or accounts[0].get(
                "rhs_account_number"
            )
            if num:
                return str(num)
        raise RhMcpNotReady(
            "rh_mcp: set RH_AGENTIC_ACCOUNT_ID — multiple accounts and no Agentic pin"
        )

    def get_open_option_positions(
        self,
        *,
        chain_symbols: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        account_number = self.resolve_account_number()
        raw = self.call_tool(
            "get_option_positions",
            {"account_number": account_number},
        )
        raw = unwrap_tool_result(raw)
        rows: list[Any]
        if isinstance(raw, list):
            rows = raw
        elif isinstance(raw, dict):
            rows = raw.get("results") or raw.get("positions") or raw.get("data") or []
            if isinstance(rows, dict):
                rows = list(rows.values())
        else:
            rows = []
        allowed = {
            s.upper() for s in chain_symbols or self.config.allowed_chain_symbols
        }
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            normalized = normalize_mcp_position(row)
            chain = str(normalized.get("chain_symbol") or "").upper()
            if allowed and chain and chain not in allowed:
                continue
            out.append(normalized)
        return out

    def get_option_chains(self, underlying_symbol: str) -> dict[str, Any]:
        """Chain metadata + expirations for one underlying.

        MCP expects ``underlying_symbol`` (single string), not ``chain_symbol``.
        Returns the matching chain dict (from ``data.chains[]``) or ``{}``.
        """
        symbol = str(underlying_symbol).upper()
        wrapped = self.call_tool(
            "get_option_chains",
            {"underlying_symbol": symbol},
        )
        raw = unwrap_tool_result(wrapped)
        chains: list[Any] = []
        if isinstance(raw, dict):
            data = raw.get("data")
            if isinstance(data, dict) and isinstance(data.get("chains"), list):
                chains = data["chains"]
            elif isinstance(raw.get("chains"), list):
                chains = raw["chains"]
            elif raw.get("symbol") or raw.get("chain_id"):
                return raw
        elif isinstance(raw, list):
            chains = raw
        for chain in chains:
            if not isinstance(chain, dict):
                continue
            if str(chain.get("symbol") or "").upper() == symbol:
                return chain
        if chains and isinstance(chains[0], dict):
            return chains[0]
        return {}

    def review_option_order(self, order: dict[str, Any]) -> dict[str, Any]:
        result = self.call_tool("review_option_order", order)
        return result if isinstance(result, dict) else {"result": result}

    def place_option_order(self, order: dict[str, Any]) -> dict[str, Any]:
        patched = dict(order)
        if self.config.agentic_account_id and not patched.get("account_id"):
            patched["account_id"] = self.config.agentic_account_id
        result = self.call_tool("place_option_order", patched)
        return result if isinstance(result, dict) else {"result": result}

    def last_read_confidence(self) -> dict[str, Any] | None:
        return self.last_read_wrap


def last_mcp_fetch_confidence() -> dict[str, Any] | None:
    """Confidence wrapper from the most recent MCP positions fetch."""
    return _last_mcp_fetch_wrap


def fetch_option_positions_via_mcp() -> tuple[list[dict[str, Any]], str | None]:
    """Return MCP option positions or ( [], error ) when not ready."""
    global _last_mcp_fetch_wrap
    if not rh_mcp_enabled():
        _last_mcp_fetch_wrap = None
        return [], None
    try:
        adapter = RobinhoodMCPAdapter()
        rows = adapter.get_open_option_positions()
        _last_mcp_fetch_wrap = adapter.last_read_confidence()
        wrap = _last_mcp_fetch_wrap
        if wrap and not mcp_read_trusted(wrap):
            tier = fusion_tier(float(wrap.get("confidence") or 0.0))
            reason = f"MCP read confidence {tier} ({wrap.get('confidence')})"
            deny_path = adapter.config.audit_log
            deny_path.parent.mkdir(parents=True, exist_ok=True)
            deny_row = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": "deny",
                "tool": "get_option_positions",
                "ok": False,
                "invariant": "I6",
                "error": reason,
                "principal": adapter._principal,
                "confidence": wrap.get("confidence"),
                "hazard_class": wrap.get("hazard_class"),
            }
            with deny_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(deny_row, default=str) + "\n")
            return [], reason
        return rows, None
    except RhMcpNotReady as exc:
        return [], str(exc)
    except RhMcpError as exc:
        return [], str(exc)
    except Exception as exc:
        logger.exception("rh_mcp fetch failed")
        return [], str(exc)
