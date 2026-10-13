# ADR-004: Decoupled Web Client & Client-Side Supabase Auth

## Status
Accepted

## Context
Originally, `web_server.py` both executed backend research pipelines and statically mounted the `web/` directory at `/css`, `/js`, and `/`. While convenient for local development, coupling static assets with the API server complicates independent frontend scaling, restricts CDN distribution, and limits deployment flexibility on Railway. Furthermore, authentication was previously unmanaged.

## Decision
Decouple the web frontend into an independent client:
1. Deploy `web/` on Railway as a dedicated static service (using Nginx Alpine or static web host).
2. Direct all client-side authentication to Supabase Auth (`@supabase/supabase-js`) using the public `SUPABASE_ANON_KEY`.
3. The frontend retrieves user JWTs and sends them as `Authorization: Bearer <token>` to the backend API (`API_BASE_URL`).
4. The backend verifies incoming tokens using `SUPABASE_JWT_SECRET` and executes user-scoped queries.

## Consequences
- **Positive:** Zero secret leakage to the client. Frontend can be deployed to CDNs (Railway, Vercel, Cloudflare Pages). Backend focuses strictly on compute and orchestration.
- **Negative:** Requires handling Cross-Origin Resource Sharing (CORS) and dynamic configuration of `API_BASE_URL`.
