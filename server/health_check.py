#!/usr/bin/env python3
# Thoth · Developed by Shayan Azmi
"""Probe a running Thoth server: /health, /ready and /api/status. Exits 0 when it answers, 1 when it does not.

Usage: python server/health_check.py [--url http://localhost:8000] [--timeout 5]

Thoth · Developed by Shayan Azmi.
"""
import argparse
import json
import sys
import time
import urllib.request


def probe(url: str, timeout: int) -> dict:
    t0 = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "thoth-health-check"}), timeout=timeout) as r:
            body = r.read().decode("utf-8")
            return {"ok": 200 <= r.getcode() < 300, "code": r.getcode(), "ms": round((time.time() - t0) * 1000), "data": json.loads(body or "{}")}
    except Exception as e:
        return {"ok": False, "code": getattr(e, "code", 0), "ms": round((time.time() - t0) * 1000), "error": str(e)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe a running Thoth server")
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--timeout", type=int, default=5)
    args = ap.parse_args()
    ok = True
    for path in ("/health", "/ready", "/api/status"):
        res = probe(args.url.rstrip("/") + path, args.timeout)
        ok &= res["ok"]
        print(f"[{'PASS' if res['ok'] else 'FAIL'}] {path:12s} HTTP {res['code']} ({res['ms']} ms)"
              + (f"  {res['error']}" if not res["ok"] else f"  {json.dumps(res['data'])[:120]}"))
    print("HEALTHY" if ok else "UNHEALTHY")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
