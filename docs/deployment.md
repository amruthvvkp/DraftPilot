# Deployment and recovery

DraftPilot is designed for a local-first Compose deployment. The application services are
restartable and store durable state in named volumes: Postgres (`pgdata`), the Temporal dev
server's SQLite history (`temporal_data`), backups and the RAG store.

## Start and verify

```bash
docker compose up -d --build
docker compose ps
curl --fail http://localhost:9000/health
curl --fail http://localhost:9001/health
curl --fail http://localhost:9010/health
docker compose exec temporal temporal operator cluster health
```

The UI is available at `http://localhost:9000`, authenticated Streamable HTTP MCP at
`http://localhost:9001/mcp`, RAG at `http://localhost:9010`, and the Temporal UI at
`http://localhost:8233`. The worker has no HTTP endpoint. Check it with
`docker compose logs --tail=100 worker`, and look for its poller on the `draftpilot` task queue in
the Temporal UI.

The `migrate` service must complete before the UI, worker, or MCP service starts. Every run and
background job is a Temporal workflow, and a restarted worker resumes it from its history. Run ids
and their status are copied into Postgres, so a browser disconnect does not cancel the operation.

The Temporal dev server suits a single-machine install. For anything shared, point
`TEMPORAL__HOST` and `TEMPORAL__NAMESPACE` at a Temporal cluster or Temporal Cloud instead.

## Configuration and secrets

Copy `.env.example` to `.env` for local configuration. Keep `.env` out of version control. Set
`SECRETS__MASTER_KEY` before storing provider credentials, and replace the database, MCP, RAG
and UI secrets before exposing any service beyond localhost. Do not publish the Temporal ports
(7233, 8233) beyond localhost: the dev server has no authentication.
Use a reverse proxy for TLS and authentication at the network edge; MCP still enforces its own
bearer token, project grant, capability, approval, redaction, timeout, and output-limit checks.

Telemetry is off by default. To collect traces, logs and metrics, start the bundled Grafana
`otel-lgtm` with `docker compose --profile observability up -d` and set `OTEL__ENABLED=true`. In
Compose, the OTLP endpoint uses the internal hostname (`http://otel-lgtm:4318`), not `localhost`.

## Backups and restore

Create an application backup before upgrades or migrations:

```bash
curl -X POST -H "Authorization: Bearer $MCP__ADMIN_TOKEN" \
  http://localhost:9000/api/v1/projects/PROJECT_ID/backups
docker compose cp ui:/data/backups ./backups
```

Backups are compressed, checksummed JSON archives. Restore always creates a new project and never
overwrites the source. Preserve `pgdata`, `backup_data`, and `rag_data` when moving the local
stack. Preserve `temporal_data` as well if in-flight workflows must survive the move.

For a disaster recovery test, stop the stack, restore the named-volume contents from an encrypted
copy, start with `docker compose up -d`, wait for `migrate` to complete, and repeat all health
checks. Validate one project backup restore and one MCP discovery/read operation before reopening
the service to clients.

## Updates and rollback

Build and apply changes in dependency order:

```bash
docker compose build ui worker mcp rag
docker compose up -d postgres redis temporal rag
docker compose run --rm migrate
docker compose up -d ui worker mcp
```

Keep the previous image tags and database backup until the smoke journey passes. Do not roll back
application code across an incompatible migration without first restoring a compatible database
backup. Review `docker compose ps`, service logs, and `/health` responses after every update.
