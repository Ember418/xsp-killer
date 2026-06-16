#!/usr/bin/env python3
"""API leg of XSP Killer super-audit: OpenRouter Fusion + Grok + DeepSeek.

Usage:
  python3 scripts/build_xsp_killer_super_audit_pack.py
  python3 scripts/run_xsp_killer_super_audit_api.py
  python3 scripts/run_xsp_killer_super_audit_api.py --models openrouter-fusion,grok-4.3-openrouter,deepseek-reasoner
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PACK = ROOT / "reports/gap-audit/pack-xsp-killer"
OUT_DIR = ROOT / "reports/gap-audit/premium-xsp-killer"


def _load_env() -> None:
    for p in (
        Path.home() / ".cemini" / "llm-routing.env",
        Path("/opt/cemini/.env"),
        ROOT / ".env",
    ):
        if not p.is_file():
            continue
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


def _call_openai_compat(
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    extra: dict | None = None,
    max_tokens: int = 24000,
) -> str:
    import httpx

    url = base_url.rstrip("/") + "/chat/completions"
    body: dict = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "XSP Killer super audit — expert options swing strategist, "
                    "execution engineer, and Cemini platform architect. "
                    "Phase A: harvest from Cemini + OSINT wiki. "
                    "Phase B: audit xsp-killer bot for bugs and profitability blockers. "
                    "Follow required output format exactly. Readonly recommendations only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    if extra:
        body.update(extra)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if "openrouter.ai" in base_url:
        headers["HTTP-Referer"] = os.environ.get(
            "OPENROUTER_HTTP_REFERER", "https://github.com/cemini23/xsp-killer"
        )
        headers["X-Title"] = os.environ.get(
            "OPENROUTER_APP_TITLE", "xsp-killer super audit"
        )
    r = httpx.post(url, headers=headers, json=body, timeout=900.0)
    r.raise_for_status()
    return (r.json()["choices"][0]["message"]["content"] or "").strip()


def _model_registry() -> dict[str, tuple[str, str, str, dict | None]]:
    or_base = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    ds_base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    return {
        "openrouter-fusion": (
            or_base,
            "OPENROUTER_API_KEY",
            "openrouter/fusion",
            {
                "plugins": [
                    {
                        "id": "fusion",
                        "analysis_models": [
                            "x-ai/grok-4.3",
                            "deepseek/deepseek-r1",
                            "google/gemini-2.5-pro-preview",
                            "anthropic/claude-sonnet-4",
                        ],
                        "model": "anthropic/claude-sonnet-4",
                    }
                ],
            },
        ),
        "grok-4.3-openrouter": (
            or_base,
            "OPENROUTER_API_KEY",
            "x-ai/grok-4.3",
            {"reasoning": {"effort": "high"}},
        ),
        "deepseek-reasoner": (
            ds_base,
            "DEEPSEEK_API_KEY",
            "deepseek-reasoner",
            None,
        ),
    }


def main() -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--models",
        default="openrouter-fusion,grok-4.3-openrouter,deepseek-reasoner",
        help="Comma-separated model labels from registry",
    )
    args = p.parse_args()

    _load_env()
    pack = args.pack.resolve()
    prompt_path = pack / "audit_prompt.md"
    if not prompt_path.is_file():
        print(f"Missing {prompt_path} — run build_xsp_killer_super_audit_pack.py first", file=sys.stderr)
        return 1

    base_prompt = prompt_path.read_text(encoding="utf-8")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")

    if args.dry_run:
        print(f"Prompt {len(base_prompt)} chars → {OUT_DIR}")
        return 0

    registry = _model_registry()
    labels = [x.strip() for x in args.models.split(",") if x.strip()]
    written: dict[str, Path] = {}

    for label in labels:
        if label not in registry:
            print(f"Unknown model label: {label}", file=sys.stderr)
            continue
        base_url, key_name, model_id, extra = registry[label]
        api_key = os.environ.get(key_name, "").strip()
        if not api_key:
            print(f"Missing {key_name} for {label}", file=sys.stderr)
            continue

        prompt = base_prompt.replace("{{MODEL_SLOT}}", label)
        print(f"Calling {label} ({model_id})...")
        try:
            text = _call_openai_compat(
                base_url=base_url,
                api_key=api_key,
                model=model_id,
                prompt=prompt,
                extra=extra,
            )
            out = OUT_DIR / f"{label}_{ts}.md"
            out.write_text(text, encoding="utf-8")
            written[label] = out
            print(f"  OK {len(text)} chars → {out.name}")
        except Exception as e:
            err_path = OUT_DIR / f"{label}_{ts}_ERROR.txt"
            err_path.write_text(str(e), encoding="utf-8")
            written[label] = err_path
            print(f"  FAIL {e}", file=sys.stderr)

    meta = {"timestamp": ts, "pack": str(pack), "models": list(written.keys())}
    (OUT_DIR / f"meta_{ts}.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta, indent=2))
    return 0 if written and all(p.suffix == ".md" for p in written.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
