# Server and deployment

Thoth runs as **one process**: `uvicorn backend.main:app` serves the API and the browser UI on the same port.

| File | Use |
|---|---|
| [`Dockerfile`](Dockerfile) | One image with the backend, the UI and the schema. The database lives on a volume at `/data`. |
| [`docker-compose.yml`](docker-compose.yml) | Run it locally with Docker: `make docker` |
| [`railway.toml`](railway.toml) | Deploy on Railway |
| [`health_check.py`](health_check.py) | Probe a running server: `make health` (exit code 0 when healthy) |

## Local

```bash
make setup     # .venv, requirements, .env
make dev       # http://localhost:8000
```

## Docker

```bash
cp .env.example .env            # add NVIDIA_API_KEY
make docker                     # or: docker compose -f server/docker-compose.yml up --build
```

The SQLite database persists in the `thoth-data` volume.

## Railway (or any container host)

1. Create a service from this repository.
2. Set the config path to `server/railway.toml` (it builds `server/Dockerfile`).
3. Add a volume mounted at `/data` so projects survive redeploys.
4. Set `NVIDIA_API_KEY` (and any optional keys from `.env.example`) as variables. `PORT` is read automatically.

The health check path is `/health`.

## Resource notes

- Model calls go to hosted APIs, so the server itself is light: one small container is enough.
- A process-wide semaphore caps concurrent model calls (the NIM free tier rejects bursts). On the free tier a
  trial reads roughly one paper a minute; a systematic review takes longer and shows its estimate before you
  approve it.
- Run one replica: the SQLite file is not shared between instances.

---

<sub>Thoth · Developed by Shayan Azmi</sub>
