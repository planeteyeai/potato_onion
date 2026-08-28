#!/usr/bin/env python3
"""Refresh feeds/agmarknet_latest.json from data.gov.in (best run from India)."""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "feeds" / "agmarknet_latest.json"
SEED = ROOT / "agmarknet_seed.json"
URL = os.environ.get(
    "LIVE_API_URL",
    "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070",
).strip()
API_KEY = (
    os.environ.get("LIVE_API_TOKEN")
    or os.environ.get("DATA_GOV_IN_API_KEY")
    or "579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b"
).strip()
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; onion-potato-feed/1.0)",
    "Accept": "application/json",
}
TIMEOUT = (25, 60)
RETRIES = 4
MAX_PAGES = 5


def page(commodity: str, offset: int = 0, limit: int = 100):
    params = {
        "api-key": API_KEY,
        "format": "json",
        "limit": limit,
        "offset": offset,
        "filters[commodity]": commodity,
    }
    last = None
    for attempt in range(RETRIES):
        try:
            r = requests.get(URL, params=params, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            payload = r.json()
            recs = payload.get("records") or payload.get("data") or []
            total = int(payload.get("total") or len(recs) or 0)
            return recs, total
        except (requests.Timeout, requests.ConnectionError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last  # type: ignore[misc]


def fetch_commodity(name: str):
    records = []
    offset = 0
    total = None
    for _ in range(MAX_PAGES):
        if offset:
            time.sleep(0.7)
        recs, page_total = page(name, offset=offset)
        if total is None:
            total = page_total
        if not recs:
            break
        records.extend(recs)
        offset += len(recs)
        if offset >= total or len(recs) < 100:
            break
    return records


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    records = []
    errors = []
    for i, com in enumerate(("Onion", "Potato")):
        if i:
            time.sleep(1.0)
        try:
            got = fetch_commodity(com)
            print(f"{com}: {len(got)} rows")
            records.extend(got)
        except Exception as e:
            print(f"{com}: FAILED {type(e).__name__}: {e}", file=sys.stderr)
            errors.append(com)

    if not records:
        print("No records fetched; leaving existing feed unchanged.", file=sys.stderr)
        return 1 if errors else 0

    # Keep exact Onion/Potato only
    records = [
        r
        for r in records
        if str(r.get("commodity", "")).strip().lower() in ("onion", "potato")
    ]
    payload = {
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "source": "cdn",
        "records": records,
        "commodities": sorted({str(r.get("commodity")) for r in records}),
        "count": len(records),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    # Keep seed in sync so cold deploys match the CDN snapshot
    seed = dict(payload)
    seed["source"] = "seed"
    SEED.write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT} ({len(records)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
