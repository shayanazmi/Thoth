#!/usr/bin/env python3
"""
Thoth Infrastructure Health Check Tool.

Probes API health endpoints, database reachability, and Redis responsiveness.
Exits with code 0 on healthy status, code 1 on failure.

Usage:
    python scripts/ops/health_check.py [--url http://localhost:8000] [--timeout 5]
"""

import os
import sys
import time
import argparse
import json
import urllib.request
import urllib.error

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

from backend.core.config import get_settings

def check_http(url: str, timeout: int = 5) -> dict:
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Thoth-HealthCheck/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            latency = (time.time() - t0) * 1000
            status_code = response.getcode()
            body = response.read().decode("utf-8")
            data = json.loads(body) if body else {}
            return {
                "ok": 200 <= status_code < 300,
                "status_code": status_code,
                "latency_ms": round(latency, 2),
                "data": data,
                "error": None
            }
    except Exception as e:
        latency = (time.time() - t0) * 1000
        return {
            "ok": False,
            "status_code": getattr(e, "code", 0),
            "latency_ms": round(latency, 2),
            "data": {},
            "error": str(e)
        }

def check_redis_direct() -> dict:
    settings = get_settings()
    if not settings.REDIS_URL:
        return {"ok": True, "type": "in-memory", "details": "Redis not configured; falling back to in-memory"}

    t0 = time.time()
    try:
        import redis
        client = redis.from_url(settings.REDIS_URL)
        client.ping()
        latency = (time.time() - t0) * 1000
        return {"ok": True, "type": "redis", "latency_ms": round(latency, 2), "details": "Ping successful"}
    except Exception as e:
        latency = (time.time() - t0) * 1000
        return {"ok": False, "type": "redis", "latency_ms": round(latency, 2), "details": str(e)}

def check_db_direct() -> dict:
    settings = get_settings()
    t0 = time.time()
    if settings.SUPABASE_URL and settings.SUPABASE_ANON_KEY:
        try:
            req = urllib.request.Request(
                f"{settings.SUPABASE_URL}/rest/v1/",
                headers={"apikey": settings.SUPABASE_ANON_KEY}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                latency = (time.time() - t0) * 1000
                return {"ok": True, "type": "supabase", "latency_ms": round(latency, 2), "details": "Connected"}
        except Exception as e:
            latency = (time.time() - t0) * 1000
            return {"ok": False, "type": "supabase", "latency_ms": round(latency, 2), "details": str(e)}

    # Check SQLite
    db_path = settings.DB_PATH
    if os.path.exists(db_path):
        return {"ok": True, "type": "sqlite", "details": f"Found at {db_path}"}
    return {"ok": True, "type": "sqlite", "details": f"Ready to initialize at {db_path}"}

def main():
    parser = argparse.ArgumentParser(description="Probe Thoth system health")
    parser.add_argument("--url", default="http://localhost:8000", help="Base backend URL")
    parser.add_argument("--timeout", type=int, default=5, help="HTTP timeout in seconds")
    args = parser.parse_args()

    print("=" * 70)
    print("THOTH SYSTEM HEALTH CHECK")
    print(f"Target: {args.url}")
    print("=" * 70)

    # 1. Check /health
    health_res = check_http(f"{args.url}/health", timeout=args.timeout)
    h_badge = "[PASS]" if health_res["ok"] else "[FAIL]"
    print(f"{h_badge} API /health endpoint: HTTP {health_res['status_code']} ({health_res['latency_ms']}ms)")
    if health_res["error"]:
        print(f"       Error: {health_res['error']}")

    # 2. Check /api/status
    status_res = check_http(f"{args.url}/api/status", timeout=args.timeout)
    s_badge = "[PASS]" if status_res["ok"] else "[FAIL]"
    print(f"{s_badge} API /api/status endpoint: HTTP {status_res['status_code']} ({status_res['latency_ms']}ms)")
    if status_res["error"]:
        print(f"       Error: {status_res['error']}")

    # 3. Direct Cache Check
    cache_res = check_redis_direct()
    c_badge = "[PASS]" if cache_res["ok"] else "[WARN]"
    print(f"{c_badge} Cache Layer ({cache_res['type']}): {cache_res['details']}")

    # 4. Direct DB Check
    db_res = check_db_direct()
    d_badge = "[PASS]" if db_res["ok"] else "[WARN]"
    print(f"{d_badge} Database Layer ({db_res['type']}): {db_res['details']}")

    print("=" * 70)
    # Overall exit code
    overall_ok = health_res["ok"] or (status_res["ok"])
    if overall_ok:
        print("RESULT: HEALTHY")
        sys.exit(0)
    else:
        print("RESULT: UNHEALTHY (Server not reachable or returning errors)")
        # If server is just not running locally, exit with non-zero
        sys.exit(1)

if __name__ == "__main__":
    main()
