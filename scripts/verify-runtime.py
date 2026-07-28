#!/usr/bin/env python3
"""Verify the local UI artifacts without starting or mutating the runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify(root: Path = ROOT) -> dict:
    checks: list[dict[str, object]] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    primary = root / "frontend" / "out" / "index.html"
    fallback = root / "frontend" / "fallback" / "index.html"
    schema = root / "docs" / "verification" / "runtime-schema.json"
    record("primary_ui", primary.is_file(), str(primary.relative_to(root)))
    record("fallback", fallback.is_file(), str(fallback.relative_to(root)))
    record("schema", schema.is_file(), str(schema.relative_to(root)))
    if fallback.is_file():
        source = fallback.read_text(encoding="utf-8")
        diagnostic_only = "Interface principale indisponible" in source and "/api/missions" not in source and "Mission autonome" not in source
        record("diagnostic_only_fallback", diagnostic_only, "fallback contains no chat or mission execution surface")
    return {"ok": all(bool(check["ok"]) for check in checks), "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Cortex Bridge runtime UI artifacts")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    result = verify()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for check in result["checks"]:
            print(f"{'PASS' if check['ok'] else 'FAIL'} {check['name']}: {check['detail']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
