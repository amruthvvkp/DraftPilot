# Deployment and recovery

DraftPilot is designed for a local-first Compose deployment. The application services are
restartable and store durable state in named volumes; the application Postgres database is
separate from the Langfuse Postgres database.

## Start and verify

```bash
docker compose up -d --build
docker compose ps
curl --fail http://localhost:9000/health
curl --fail http://localhost:9001/health
curl --fail http://localhost:9010/health
curl --fail http://localhost:3300/api/public/health
```

The UI is available at `http://localhost:9000`, authenticated Streamable HTTP MCP at
`http://localhost:9001/mcp`, RAG at `http://localhost:9010`, and Langfuse at
`http://localhost:3300`. The ARQ worker has no HTTP endpoint; verify it with
`docker compose logs --tail=100 worker` and inspect persisted workflow runs through the API.

The `migrate` service must complete before the UI, worker, or MCP service starts. A restarted
worker requeues runs that were interrupted during shutdown. Run IDs and their status remain in
Postgres, so a browser disconnect does not cancel the operation.

## Configuration and secrets

Copy `.env.example` to `.env` for local configuration. Keep `.env` out of version control. Set
`SECRETS__MASTER_KEY` before storing provider credentials, and replace all `CHANGEME` Langfuse,
database, Redis, MinIO, MCP, RAG, and UI secrets before exposing any service beyond localhost.
Use a reverse proxy for TLS and authentication at the network edge; MCP still enforces its own
bearer token, project grant, capability, approval, redaction, timeout, and output-limit checks.

For Langfuse, set `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL` for the
browser/API client and configure the matching base64 `OTEL_EXPORTER_OTLP_HEADERS`. In Compose,
the OTLP endpoint must use the internal hostname `langfuse-web`, not `localhost`.

## Backups and restore

Create an application backup before upgrades or migrations:

```bash
curl -X POST -H "Authorization: Bearer $MCP__ADMIN_TOKEN" \
  http://localhost:9000/api/v1/projects/PROJECT_ID/backups
docker compose cp ui:/data/backups ./backups
```

Backups are compressed, checksummed JSON archives. Restore always creates a new project and never
overwrites the source. Preserve `pgdata`, `backup_data`, and `rag_data` when moving the local
stack. Preserve the Langfuse volumes separately if trace history is part of the recovery point.

For a disaster recovery test, stop the stack, restore the named-volume contents from an encrypted
copy, start with `docker compose up -d`, wait for `migrate` to complete, and repeat all health
checks. Validate one project backup restore and one MCP discovery/read operation before reopening
the service to clients.

## Updates and rollback

Build and apply changes in dependency order:

```bash
docker compose build ui worker mcp rag
docker compose up -d postgres redis rag
docker compose run --rm migrate
docker compose up -d ui worker mcp
```

Keep the previous image tags and database backup until the smoke journey passes. Do not roll back
application code across an incompatible migration without first restoring a compatible database
backup. Review `docker compose ps`, service logs, and `/health` responses after every update.
