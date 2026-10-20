# Stateless catalog MVP — Next.js + FastAPI + aiogram + PostgreSQL + MinIO

A small catalog service for the practical assignment. It intentionally avoids AI/LLM dependencies and keeps durable state in PostgreSQL and MinIO, not in container files or Python process memory.

## Features

- Next.js App Router catalog, rendered on the server and available in a normal browser.
- Telegram Mini App SDK integration (`ready()` / `expand()`).
- FastAPI async API backed by PostgreSQL (`asyncpg`).
- Product creation from an admin Telegram message containing a photo and caption (caption is the product name).
- Product images are stored in MinIO; product records are stored in PostgreSQL.
- aiogram 3 webhook mode, so multiple bot replicas can sit behind a public reverse proxy/load balancer.
- API product creation is idempotent per Telegram `chat_id + message_id`, which prevents duplicate products when Telegram retries a webhook update.
- Non-root runtime users, multi-stage Docker images, health endpoints, parameterized SQL, and external persistent storage.

## Run locally

1. Install Docker Engine and Docker Compose plugin.
2. Copy the environment template and change the secrets:

   ```bash
   cp .env.example .env
   ```

3. Set `BOT_TOKEN` and `ADMIN_TELEGRAM_IDS` if you want to test Telegram product creation. `ADMIN_TELEGRAM_IDS` is the comma-separated numeric Telegram user ID list allowed to add products.
4. Run the stack:

   ```bash
   docker compose up --build
   ```

5. Open <http://localhost:3000>. The local reverse proxy is also configured to forward `/telegram/webhook` to the bot. FastAPI documentation is available at <http://localhost:3000/docs>. MinIO console is at <http://127.0.0.1:9001> (credentials come from `.env`). Product images are served through the reverse proxy at `/catalog/...`; this makes them reachable on the same public host as the Mini App.

The catalog website and API can run without a Telegram bot token. To use the Telegram bot, expose the `bot` service behind an HTTPS endpoint and configure `BOT_WEBHOOK_BASE_URL` to that public base URL. The reverse proxy should forward `/telegram/webhook` to `bot:8080/telegram/webhook`. Set `WEBAPP_URL` to the public HTTPS URL of the Next.js app; Telegram Mini Apps require a reachable HTTPS origin. A local `localhost:3000` URL is not reachable from Telegram clients.

## Multi-replica test

Once environment settings are configured, scale the stateless application services:

```bash
docker compose up --build --scale api=2 --scale web=2 --scale bot=2
```

`api`, `web`, and `bot` intentionally have no host-published ports, so scaling does not cause port collisions. The included Nginx proxy publishes port 3000 and forwards website requests to `web` and Telegram webhook requests to `bot` using Docker DNS. A public webhook must route to the bot service. In a real cluster, use the same external PostgreSQL and MinIO endpoints for every replica.

The bot uses webhooks rather than polling specifically to avoid multiple pollers competing for the same Telegram bot token. To receive live Telegram updates, configure a public HTTPS tunnel/reverse proxy and set `BOT_WEBHOOK_BASE_URL` and `WEBAPP_URL` to that public hostname; the local HTTP proxy alone is not internet-accessible.

## API

- `GET /health` — health check.
- `GET /api/products?limit=50&offset=0` — catalog.
- `GET /api/products/{id}` — product details.
- `POST /api/admin/products` — JSON body with `title`, `image_base64`, and optional `source_chat_id` / `source_message_id`, authenticated by `X-Admin-Token`. The JSON/base64 upload is held in memory and avoids writing image content to container disk. The Telegram source fields provide idempotency for webhook retries.

## Notes

- Change all example secrets before deploying.
- Configure TLS, HTTPS, rate limiting, logging, backups, and proper secret management in production.
- The MinIO public read policy is intended for catalog product images only. Do not store private files in this bucket. Configure `MINIO_PUBLIC_URL` to the public HTTPS base URL in deployment; the proxy exposes only the public-read bucket path, not the MinIO API port.
- DB initialization SQL is mounted into PostgreSQL's first-time initialization. If you reuse an existing database volume after changing DDL, apply migrations deliberately; the init file is not re-run on an already-initialized volume.
