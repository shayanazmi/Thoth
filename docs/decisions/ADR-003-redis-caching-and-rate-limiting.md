# ADR-003: Redis Caching & Token Bucket Rate Limiting

## Status
Accepted

## Context
Autonomous multi-agent research pipelines issue repeated queries across academic search engines (ArXiv, Semantic Scholar, Tavily) and large language model inference providers (NVIDIA NIM, Groq, OpenAI). Without centralized caching and rate-limiting, concurrent research sessions rapidly trigger HTTP 429 quota exhaustion and incur redundant latency. The previous implementation used an SQLite `http_cache` table which does not scale across instances.

## Decision
Introduce **Redis** (Railway Add-on or managed Redis instance) as the primary caching and rate-limiting backbone:
1. Cache academic queries and web scrape results with namespaced keys and 24h TTLs.
2. Implement a **Token Bucket** algorithm in Redis for egress LLM calls and per-user ingress rate limits.
3. Build **Fail-Open Resilience**: If Redis becomes unreachable, the cache manager seamlessly switches to a local in-memory LRU without aborting active research execution.

## Consequences
- **Positive:** Sub-2ms cache hits for recurring research topics. Zero quota exhaustion crashes. Resilient failover.
- **Negative:** Adds Redis as an infrastructure dependency.
