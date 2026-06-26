#!/usr/bin/env python3
"""API leg of XSP Killer super-audit: OpenRouter models in parallel.

Replaces DeepSeek Reasoner with GLM 5.2 on OpenRouter when available;
falls back to openrouter/fusion if GLM call fails.

Usage:
  python3 scripts/build_xsp_killer_super_audit_pack.py
  python3 scripts/run_xsp_killer_super_audit_api.py
  python3 scripts/run_xsp_killer_super_audit_api.py --models glm-5.2-openrouter,grok-4.3-openrouter,openrouter-fusion
"""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PACK = ROOT / "reports/gap-audit/pack-xsp-killer-v3"
OUT_DIR = ROOT / "reports/gap-audit/premium-xsp-killer-v3"


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
                    "XSP Killer super audit v3 — expert options swing strategist, "
                    "quantitative options math, execution engineer, and Cemini platform architect. "
                    "Phases A–E: harvest, bot audit, variant soak, strategy math, efficiency tuning. "
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
            "OPENROUTER_APP_TITLE", "xsp-killer super audit v3"
        )
    r = httpx.post(url, headers=headers, json=body, timeout=900.0)
    r.raise_for_status()
    content = (r.json()["choices"][0]["message"]["content"] or "").strip()
    if not content:
        raise RuntimeError(f"Empty response body from {model}")
    return content


def _model_registry() -> dict[str, tuple[str, str, str, dict | None]]:
    or_base = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
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
                            "z-ai/glm-5.2",
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
        "glm-5.2-openrouter": (
            or_base,
            "OPENROUTER_API_KEY",
            "z-ai/glm-5.2",
            None,
        ),
        "google-gemini-2.5-pro": (
            or_base,
            "OPENROUTER_API_KEY",
            "google/gemini-2.5-pro-preview",
            None,
        ),
        "claude-sonnet-4-openrouter": (
            or_base,
            "OPENROUTER_API_KEY",
            "anthropic/claude-sonnet-4",
            None,
        ),
    }


def _run_one(label: str, base_prompt: str, ts: str) -> tuple[str, Path, str | None]:
    registry = _model_registry()
    if label not in registry:
        return (
            label,
            OUT_DIR / f"{label}_{ts}_ERROR.txt",
            f"Unknown model label: {label}",
        )

    base_url, key_name, model_id, extra = registry[label]
    api_key = os.environ.get(key_name, "").strip()
    if not api_key:
        err = OUT_DIR / f"{label}_{ts}_ERROR.txt"
        err.write_text(f"Missing {key_name}", encoding="utf-8")
        return label, err, f"Missing {key_name}"

    prompt = base_prompt.replace("{{MODEL_SLOT}}", label)
    print(f"Calling {label} ({model_id})...", flush=True)
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
        print(f"  OK {label} → {len(text)} chars", flush=True)
        return label, out, None
    except Exception as e:
        err_path = OUT_DIR / f"{label}_{ts}_ERROR.txt"
        err_path.write_text(str(e), encoding="utf-8")
        print(f"  FAIL {label}: {e}", flush=True)
        return label, err_path, str(e)


def main() -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--models",
        default=(
            "glm-5.2-openrouter,grok-4.3-openrouter,google-gemini-2.5-pro,"
            "claude-sonnet-4-openrouter,openrouter-fusion"
        ),
        help="Comma-separated model labels from registry",
    )
    p.add_argument("--workers", type=int, default=5, help="Parallel API workers")
    args = p.parse_args()

    _load_env()
    pack = args.pack.resolve()
    prompt_path = pack / "audit_prompt.md"
    if not prompt_path.is_file():
        print(
            f"Missing {prompt_path} — run build_xsp_killer_super_audit_pack.py first",
            file=sys.stderr,
        )
        return 1

    base_prompt = prompt_path.read_text(encoding="utf-8")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")

    if args.dry_run:
        print(f"Prompt {len(base_prompt)} chars → {OUT_DIR}")
        return 0

    labels = [x.strip() for x in args.models.split(",") if x.strip()]
    written: dict[str, Path] = {}
    errors: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=min(args.workers, len(labels))) as pool:
        futures = {
            pool.submit(_run_one, label, base_prompt, ts): label for label in labels
        }
        for fut in as_completed(futures):
            label, path, err = fut.result()
            written[label] = path
            if err:
                errors[label] = err

    # GLM fallback → fusion if GLM failed
    glm_err = errors.get("glm-5.2-openrouter")
    if glm_err and "openrouter-fusion" not in written:
        print("GLM 5.2 failed — retrying with openrouter-fusion...", flush=True)
        label, path, err = _run_one("openrouter-fusion", base_prompt, ts)
        written[label] = path
        if err:
            errors[label] = err

    meta = {
        "timestamp": ts,
        "pack": str(pack),
        "models": list(written.keys()),
        "errors": errors,
        "prompt_chars": len(base_prompt),
    }
    (OUT_DIR / f"meta_{ts}.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(meta, indent=2))
    ok = sum(1 for p in written.values() if p.suffix == ".md")
    return 0 if ok >= 3 else 1


if __name__ == "__main__":
    raise SystemExit(main())
