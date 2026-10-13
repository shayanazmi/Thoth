# 📖 Thoth Production Runbook & Operations Manual

This runbook provides on-call procedures, incident mitigation steps, health inspection protocols, and disaster recovery workflows for the Thoth platform.

---

## 1. System Health Verification

### Endpoint Probes
- **Liveness Probe:** `GET /health`
  - Expected: HTTP 200 `{"status": "healthy", "service": "thoth-backend", "timestamp": "..."}`
  - Used by Railway to verify that the container is responsive.
- **Readiness Probe:** `GET /ready`
  - Expected: HTTP 200 `{"status": "ready", "redis": "connected", "database": "connected"}`
  - Returns HTTP 503 if critical dependencies are uncontactable.

### Comprehensive Diagnostic Run
Run the 7-layer diagnostic script to audit all system subsystems:
```bash
python scripts/dev/diagnostic_test.py
```
This tests:
1. Environment & credentials
2. LLM inference & fallback latency
3. Scholar retrieval (ArXiv, Semantic Scholar, Tavily)
4. Knowledge Vault indexing and graph relations
5. SLM Truth Guard claim verification
6. Multi-turn token budgeting
7. Epistemic philosopher desk matching

---

## 2. Incident Response Playbooks

### Incident 1: Upstream LLM Rate Limit Exhaustion (HTTP 429)
**Symptom:** Logs report repeated 429 errors from NVIDIA NIM.
**Root Cause:** The project has exhausted its current RPM / TPM tier on NVIDIA.
**Mitigation:**
1. Check `GROQ_API_KEY` in environment variables:
   ```bash
   railway variables get GROQ_API_KEY
   ```
2. Verify that fallback routing triggered: check logs for `[WARN] Switching to fallback provider: groq`.
3. If Groq is also rate-limited, ensure `OPENAI_API_KEY` is set to enable tertiary fallback.
4. Temporarily throttle user research concurrency by tuning `TokenBucketLimiter` capacity in `backend/core/rate_limit.py`.

### Incident 2: Redis Disconnection / Out of Memory
**Symptom:** Logs show `[WARNING] Redis unavailable ... Operating in memory-fallback mode`.
**Impact:** Zero downtime. Thoth automatically switches to local memory caching.
**Mitigation:**
1. Check Redis memory usage in Railway Dashboard.
2. If Redis is down, restart the Railway Redis add-on.
3. Flush cache if memory is full:
   ```bash
   python scripts/ops/cache_flush.py --all --force
   ```

### Incident 3: Supabase Authentication Failure (HTTP 401 on All API Calls)
**Symptom:** Web client reports authentication errors; `/api/` calls return 401 Unauthorized.
**Mitigation:**
1. Verify `SUPABASE_JWT_SECRET` matches the Supabase Dashboard (`Project Settings -> API -> JWT Settings -> JWT Secret`).
2. Verify system clocks are synchronized (NTP drift can cause `jwt.ExpiredSignatureError`).
3. Check if user token expired on client; inspect `localStorage` in browser dev tools.

### Incident 4: High Hallucination / Verifier Flagging Rate
**Symptom:** Reports consistently show `Verification Status: FAILED (FLAGGED FOR REVISION)`.
**Mitigation:**
1. Inspect the extracted source files in `vault/sources/`. Ensure scrapers are extracting complete text, not bot-detection challenges or empty HTML.
2. Verify Tavily search queries are properly formed.
3. Check `GROQ_VERIFIER_MODEL` (defaults to `openai/gpt-oss-20b`); ensure model is online.

---

## 3. Database Maintenance & Backups

### Supabase Point-in-Time Recovery
- Supabase automatically manages daily backups. Point-in-time recovery (PITR) is accessible from the Supabase dashboard under **Database → Backups**.

### Manual Database Snapshot
```bash
pg_dump --host=db.<project_ref>.supabase.co --username=postgres --dbname=postgres -F c -f thoth_backup_$(date +%Y%m%d).dump
```
