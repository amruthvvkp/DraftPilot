# Frontend

The studio is a React 19 + Vite + TypeScript single-page app in `frontend/src`. `npm run build`
type-checks (`tsc --noEmit`) and writes `frontend/dist`, which the web process serves (see
[Architecture](architecture.md#serving-the-studio)). `npm run dev` starts the Vite dev server on
:5173 and proxies `/api` to the API on :8000.

## Bootstrapping

`main.tsx` applies the saved appearance (`initAppearance()`), creates the query client and renders:

```
StrictMode → QueryClientProvider → BrowserRouter → AuthGate → App
```

`AuthGate` (`SignIn.tsx`) asks for `API__TOKEN` when the API requires one. A 401 from any request
dispatches an auth-required event that re-locks the app. `App` loads the writer profile once and
applies its saved appearance, then renders `AppRoutes`.

## Routing

Routes are declared in `AppRoutes` in `App.tsx` (react-router 7, declarative mode):

| Path | Page |
|---|---|
| `/settings` | `ProviderSettings` |
| `/projects` (and any unknown path) | `ProjectVault`, the project library |
| `/projects/:projectId` | `ProjectLayout`, the project shell (numeric ids only; anything else redirects to `/projects`) |
| … index, `script` | `Workspace`, the script editor |
| … `timeline` | `Workspace` opened on the timeline |
| … `storyline` | `StorylinePage` |
| … `characters`, `characters/:characterId` | `CharactersPage` with `CharacterDetail` |
| … `locations` | `LocationsPage` |
| … `outline`, `beats` | `OutlinePage` |
| … `context-map` | `ContextMapPage` |
| … `studio` | `ArtifactStudio` |
| … `context` | `KnowledgeGraph` |
| … `room` | `WritersRoom` |
| … `twin` | `StoryTwin` |
| … any other sub-path | redirects to `/projects/:projectId` |

Older pages take `projectId` as a prop; `withProject(Page)` reads it from the URL with
`useProjectId()` and remounts the page when the project changes. Newer pages under `project/` call
`useProjectId()` themselves. Navigate with `Link`, `NavLink` or `useNavigate`, never
`location.assign`.

## Project shell

`project/ProjectLayout.tsx` wraps every project page. It renders:

- the **stepper**, Storyline → Characters → Outline → Script, one `NavLink` per stage. Each stage
  shows a state (`empty`, `started` or `done`) computed by `projectStages()` in
  `project/progress.ts` from the storyline, characters, beats and workspace;
- the **tools nav**: Context map, Locations, Story twin, Writers' room, Story studio and Knowledge
  graph;
- the **chat dock rail**, with `ChatDock` lazy-loaded;
- the routed page in an `Outlet`.

The shell also calls `useProjectLiveSync(projectId)`, so every page of an open project stays live.

The **Context map** (`project/ContextMapPage.tsx`) shows what the agents will see: the exact
Story-twin brief, plus every gap per stage from `projectStages()`, each linking to the page that
fills it.

## Data layer

Server state goes through TanStack Query. `data/queries.ts` holds the query client, the query keys
and one hook per resource (`useProjects`, `useWorkspace`, `useStoryline`, `useCharacters`,
`useTimeline`, `useRelationships`, `useLocations`, `useBeats`, `useTwin`, `useArtifacts`).

- `createQueryClient()` sets a 5 s `staleTime`, no refetch on window focus (it would clobber
  typing), no retries on 4xx errors, and no mutation retries.
- Every key for one project starts with `['project', id]` (see `keys`), so invalidating that prefix
  refreshes the whole project.
- `useWorkspace` reads the draft from `?draft=<screenplay id>` (`useDraftId`) and keeps the previous
  draft on screen while another loads.
- `errorMessage()` turns a thrown value into writer-facing text and explains a 409 edit conflict.

### Live sync

`useProjectLiveSync` (`data/liveSync.ts`) subscribes to the project's SSE stream,
`/api/v1/projects/:id/events`, via `subscribeProjectEvents()` in `api.ts`. One `EventSource` per
project is shared by every subscriber and closed when the last one leaves. Each event goes to
`invalidateForEvent()`, which invalidates the keys `staleKeysFor()` maps it to, for example:

| Event | Invalidates |
|---|---|
| `scene.changed` | workspaces, twin |
| `structure.changed` | workspaces, beats, characters, locations, timelines |
| `story.changed` | the keys for `data.kind` (`character`, `timeline_event`, `relationship`, `location`, `beat`), else the whole project; always the twin |
| `project.changed` | storyline, workspaces, twin, the project list |
| `twin.changed` | twin, characters, locations |
| `proposal.changed` | proposals |
| `run.changed`, `workflow.progress` | runs |

Active queries refetch; inactive ones refetch when next used. When you add a query, give it a key
under `['project', id]` and add it to `staleKeysFor()` for the events that change it.

## API clients

- `api.ts` is the typed fetch client. Every call goes through `request<T>()`, which sends
  same-origin credentials and an `X-DraftPilot-Client` tab id, defaults to a JSON content type,
  returns `undefined` for 204, and throws `ApiError(status, detail)` from the API's `detail`.
- `storyApi.ts` is the typed client for the story domain (storyline, characters, timelines,
  relationships, locations, beats), built on `request()`. Writes send the row's `version` as
  `If-Match`, so a stale edit fails with 409.

## Chat dock

`frontend/src/chat/` is the persistent chat with the room, an [AG-UI](https://docs.ag-ui.com)
client of `POST /api/v1/projects/:id/room/chat` (see [Chat](../chat.md)).

- **Transport** (`transport.ts`): `streamRun()` runs an `@ag-ui/client` `HttpAgent` with a fetch
  that adds credentials and the tab id and maps errors to `ApiError`. Stop aborts the stream.
- **Session** (`useChatSession.ts`): builds each `RunAgentInput` (thread id, messages, frontend
  tools, and `forwardedProps` carrying role, permission mode, provider profile, current page and the
  page's focus from `focus.ts`), and handles send, stop, retry, regenerate, approvals and threads.
- **Reducer** (`reducer.ts`): `chatReducer` folds AG-UI events (`RUN_*`, `TEXT_MESSAGE_*`,
  `REASONING_MESSAGE_*`, `TOOL_CALL_*`) into entries (user, text, reasoning, tool) and tracks
  approval interrupts and the writer's decisions. When every interrupt is decided the session
  resumes the run.
- **Frontend tools** (`FRONTEND_TOOLS` in `ChatDock.tsx`): `navigate` opens a studio path (only
  paths under `/projects` or `/settings`), and `open_scene` opens `/projects/:id?scene=<scene_id>`
  in the script editor. When a run ends with pending calls to these tools, the dock runs them with
  `runTool` and starts a follow-up run carrying the results as tool messages.
- **Generative UI** (`registry.tsx`, `cards.tsx`): `TOOL_CARDS` maps tool calls to cards. The first
  rule that matches wins, and anything unmatched renders `GenericCard`, a collapsible chip with the
  arguments and result.
- Pages report what the writer is looking at with `useChatFocus(artifact, selection, sceneId)`;
  the dock sends it with every turn.

## Theming

`theme.css` defines the tokens: every colour is a CSS custom property (`--surface*`, `--ink*`,
`--line*`, `--accent*`, `--danger*`, `--success*`, `--chrome*`, ...). `[data-theme="paper"]`,
`"slate"` and `"night"` redefine them, and the accent variants are derived from `--accent` with
`color-mix`. `theme.ts` applies an appearance (theme `system | paper | slate | night` plus an
accent hex) by setting `data-theme` and `--accent` on `<html>`, stores it in `localStorage`, and
follows the OS for `system`. Use the tokens in new CSS; do not hard-code colours. Styles are plain
CSS in `src/*.css`.

## Tests

- **Vitest** unit and component tests live next to the code as `src/**/*.test.ts(x)` and run in
  happy-dom with Testing Library (`vitest.config.ts`). `npm --prefix frontend run test` watches;
  `npm --prefix frontend run test:run` runs once.
- **Playwright** browser journeys are Python tests in `tests/e2e`. Most mock the API with
  `page.route`; the real-stack journeys (`test_real_stack.py`, `test_manual_journey.py`) are marked
  `stack` and run with `uv run pytest tests/e2e -m stack` against a running stack. Tests select by
  role and accessible name, so give every control one.

## Add a page

1. Create the component under `frontend/src/project/` (project pages) and read the project with
   `useProjectId()`.
2. Fetch through a hook in `data/queries.ts`, with a key under `['project', id]`; add the key to
   `staleKeysFor()` for the live-sync events that change it.
3. Register the route in `AppRoutes` in `App.tsx`, nested under `/projects/:projectId` so it gets
   the shell.
4. Link to it from `ProjectLayout.tsx` (the tools nav), or from a stage in `progress.ts`.
5. If the agent should be able to open it, mention the path in the `navigate` tool description in
   `ChatDock.tsx`.
6. Add a Vitest test beside it and, for a user journey, a Playwright test in `tests/e2e`.

## Add a generative-UI card

1. Write the card in `chat/cards.tsx` as a component taking `CardProps`
   (`{ call, args, result, projectId }`); wrap it in `CardShell` for the shared title and working
   state, and check `call.status` (`'done'` once the result has arrived).
2. Add a rule to `TOOL_CARDS` in `chat/registry.tsx`:
   `{ match: (call, args, result) => call.name === 'my_tool', card: MyCard }`. Order matters: put
   specific rules before broad ones such as the `propose_*` rule.
3. Give the tool a writer-facing name in `TOOL_LABELS` (`chat/labels.ts`).
4. Cover the match in `chat/registry.test.tsx`.
