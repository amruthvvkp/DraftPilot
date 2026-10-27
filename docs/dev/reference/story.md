# Story domain

The typed story behind the guided flow (storyline → characters → outline → script): the models,
the services REST, MCP and the writers' room share, the reviewable proposals agents make against
them, and whole-project backup and restore.

## Models

Writer-owned canonical records: characters with their timelines and relationships, locations and
beats. The Twin Keeper also derives characters and locations from the draft.

::: draftpilot.models.story

## Story services

`draftpilot.core.story` holds one service per concern. `entities` describes every typed entity kind
once (in `KINDS`) and validates project scope, cross references and the caller's version on every
write. `storyline` owns the project brief and storyline. `structure` owns acts, scenes and blocks,
keeps positions contiguous and runs the side effects (scene RAG refresh, live-sync event, debounced
Story-twin refresh).

::: draftpilot.core.story

::: draftpilot.core.story.entities

::: draftpilot.core.story.storyline

::: draftpilot.core.story.structure

## Story proposals

An agent never writes the typed story directly: it proposes a create, update or delete of an
entity, or a storyline edit, and the writer approves (applied as the writer), rejects, or later
rolls back an approved change.

::: draftpilot.core.story.proposals

## Agent proposals

Typed agent proposals in general, and versioned scene-reorder (timeline) proposals. Both share the
create → approve / reject → rollback lifecycle.

::: draftpilot.core.proposals

::: draftpilot.core.timeline_proposals

## Project backup

Serialise a whole project to a portable payload and restore it into a new project. Database ids
never leave the payload as references; artifacts, story entities, acts and scenes carry their own
backup-local identifiers instead.

::: draftpilot.core.project_backup
