"""CLI smoke probe for configured remote MCP providers.

Run::

    python -m amazon_create.mcp.remote_probe

Probes SellerSprite and Sorftime when their keys are set in the environment
or project ``.env``. Writes redacted JSON to stdout; never prints secrets.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Final

import anyio

from amazon_create.config import Settings
from amazon_create.mcp.remote_http import (
    RemoteProbeSummary,
    endpoints_from_settings,
    probe_remote_mcp,
)

_EVIDENCE_DEFAULT: Final[Path] = Path(r"D:\demo\.omo\evidence\mcp-live-probe.json")


async def probe_configured(
    settings: Settings | None = None,
    *,
    call_safe_tool: bool = True,
) -> list[RemoteProbeSummary]:
    """Probe every remote MCP endpoint that has a non-empty key."""
    cfg = settings if settings is not None else Settings()
    endpoints = endpoints_from_settings(cfg)
    return [
        await probe_remote_mcp(
            endpoint,
            call_safe_tool=call_safe_tool,
            timeout_s=cfg.remote_mcp_timeout_seconds,
        )
        for endpoint in endpoints
    ]


def write_evidence(
    results: list[RemoteProbeSummary],
    path: Path | None = None,
) -> Path:
    """Write redacted probe results to an evidence JSON file."""
    target = path if path is not None else _EVIDENCE_DEFAULT
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "providers": results,
        "summary": {
            name: ("PASS" if item["ok"] else "FAIL") for item in results for name in (item["name"],)
        },
    }
    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


async def _async_main(argv: list[str]) -> int:
    write_path: Path | None = None
    if "--evidence" in argv:
        idx = argv.index("--evidence")
        if idx + 1 < len(argv):
            write_path = Path(argv[idx + 1])
        else:
            write_path = _EVIDENCE_DEFAULT

    results = await probe_configured()
    if not results:
        print(
            json.dumps(
                {
                    "providers": [],
                    "summary": {},
                    "note": "No remote MCP keys configured; fixture path remains default.",
                },
                indent=2,
            )
        )
        return 0

    text = json.dumps({"providers": results}, indent=2, ensure_ascii=False)
    print(text)
    if write_path is not None:
        out = write_evidence(results, write_path)
        print(f"evidence_written={out}", file=sys.stderr)

    return 0 if all(item["ok"] for item in results) else 1


def main(argv: list[str] | None = None) -> int:
    """Sync entrypoint for ``python -m amazon_create.mcp.remote_probe``."""
    args = list(sys.argv[1:] if argv is None else argv)
    return anyio.run(_async_main, args)


if __name__ == "__main__":
    raise SystemExit(main())
