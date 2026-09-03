# Backups and recovery

DraftPilot stores project backups as compressed JSON archives under `BACKUP__ROOT`.
Each archive contains a schema version, project id, creation time, application version, and
SHA-256 checksum. Writes are atomic: the temporary archive is replaced only after the complete
payload has been written.

The API is project-scoped:

```text
POST /api/v1/projects/{project_id}/backups
GET  /api/v1/projects/{project_id}/backups
GET  /api/v1/projects/{project_id}/backups/{filename}
POST /api/v1/projects/{project_id}/backups/{filename}/restore
```

Restore validates the archive and creates a new project. It never overwrites the source project.
The Compose UI mounts `backup_data` at `/data/backups`; preserve that volume when upgrading or
moving the local stack. Keep backups outside the application container in production and copy
them to an independent encrypted location for disaster recovery.
