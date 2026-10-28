---
icon: lucide/archive-restore
---

# Backups & recovery

A backup is a snapshot of one project in a single file. You can make one whenever you like, and
DraftPilot makes one for you every time you delete a project. Restoring a backup **always creates a
new project**: your current work is never overwritten.

## Back up a project

Open the project's **Script** page. In the header, next to **Import** and the export links:

- **Backup** writes a new backup now. The header confirms it with **Backup ready:** and the file
  name.
- **Backups** opens the **Project backups** drawer, which lists every backup of this project with
  its date and the start of its SHA-256 checksum.

Each row in the drawer has two actions:

- **Download** saves the backup file (a `.json.gz` archive) to your computer;
- **Restore copy** creates a new project from that backup and opens it.

Make a backup before a big rewrite, before letting the room work on the whole project, and before
you upgrade DraftPilot.

## What a backup holds

| Included | Not included |
|---|---|
| The project and its storyline: title, logline, premise, synopsis, theme, tone, notes, genres, languages, format, project instruction | The knowledge graph (canon nodes and links) |
| The typed creative references | Chat conversations |
| Every draft, with its acts, scenes and blocks | Scene snapshots (revision history) |
| Story artifacts, with their versions, stale flags, metadata and dependency links | Saved dialogue translations |
| Characters, locations, beats, timeline events and relationships | Proposals, room runs and evaluations |

Links between story records survive a restore: a timeline event still belongs to its character, a
beat still points at its scenes, and an artifact still depends on the artifacts it was built from.
Backups made before characters and the outline were typed records simply restore without them.

## Delete a project

In **Projects**, open a project card's **⋯** menu and choose **Delete…**. To confirm, type the
project's title exactly and press **Delete project**.

Deleting removes everything in the project: every draft, scene, artifact, run, proposal and
conversation. DraftPilot writes a backup first, so the project appears under **Recently deleted**.
What that backup does not hold (see the table above) is gone for good; the delete dialog lists it
before you confirm.

## Restore a deleted project

**Recently deleted**, at the bottom of **Projects**, lists each deleted project with the time it was
deleted.

- **Restore** brings the project back from its last backup, as a new project with the same title.
  It then leaves the list.
- **Dismiss** hides it from the list. The backup files stay on disk.

## Duplicate a project

In a project card's **⋯** menu, **Duplicate** creates a copy named "*title* (copy)". The copy holds
the same content as a backup (brief, references, artifacts, every draft and the story records) and
is a separate project from then on. Use it to try a radical version without touching the original.

## Where backups live

Backups are files in the folder set by `BACKUP__ROOT`. In the Compose stack that is `/data/backups`
on the `backup_data` volume, which the `ui`, `mcp` and `worker` containers all mount. A backup made
over MCP therefore shows up in the studio's **Backups** drawer, and an export stored over MCP
(`create_screenplay_export`) lands in `/data/backups/exports` on the same volume.

If you run the MCP server outside Compose (for example `draftpilot mcp` on your machine), point its
`BACKUP__ROOT` at the same folder as the studio's, or its backups will not appear in the studio.

!!! note "Keep your backups safe"
    Keep the `backup_data` volume when you upgrade or move the stack. For real safety, copy the
    files somewhere else as well, for example with `docker compose cp ui:/data/backups ./backups`,
    and store that copy encrypted.

Every archive records its schema version, the project it came from, when it was made, the
DraftPilot version, and a SHA-256 checksum of its contents. A backup is written to a temporary file
first and only takes its final name once it is complete, so a crash never leaves half a backup.

## From the API

```text
POST /api/v1/projects/{project_id}/backups                      # create
GET  /api/v1/projects/{project_id}/backups                      # list
GET  /api/v1/projects/{project_id}/backups/{filename}           # download
POST /api/v1/projects/{project_id}/backups/{filename}/restore   # restore into a new project
POST /api/v1/projects/{project_id}/duplicate                    # optional body: {"title": "..."}
DELETE /api/v1/projects/{project_id}                            # back up, then delete
GET  /api/v1/projects/deleted                                   # "Recently deleted"
POST /api/v1/projects/deleted/{project_id}/dismiss
```

Restore checks the archive before it creates anything and answers `422` for an invalid file. It
returns `{"project_id": …}` for the new project. Artifact dependency links are remapped to the new
artifacts; older archives that did not record artifact ids restore without those links. After a
restore or duplicate, the new project's content is queued for indexing so the room can search it.
Over MCP, `list_project_backups`, `create_project_backup` and `restore_project_backup` do the same
([MCP integration](mcp.md)).
