# Frontend — React/Vite studio

- `src/main.tsx` mounts `<AuthGate><App/></AuthGate>`. `SignIn.tsx` asks for `API__TOKEN` when the
  API requires it, and a 401 from `api.ts` re-locks the app.
- Routes are declared in `src/App.tsx` (`AppRoutes`, react-router 7 declarative mode). Project pages
  nest under `project/ProjectLayout.tsx` (the Storyline → Characters → Outline → Script stepper, the
  tools nav and the chat dock rail). Navigate with `Link`/`useNavigate`, never `location.assign`.
- Data goes through TanStack Query hooks in `src/data/queries.ts`; `useProjectLiveSync`
  (`src/data/liveSync.ts`) invalidates them from the project's SSE events. The typed story client
  is `src/storyApi.ts`.
- `src/api.ts` is the typed fetch client. Every call goes through `request()`, which sends
  same-origin credentials and turns API errors into `ApiError(status, detail)`.
- Styles are plain CSS in `src/*.css`. Static assets and favicons live in `public/`.
- Build with `npm run build` (runs `tsc --noEmit`, then Vite). The web process serves `dist/`.
  `compose.dev.yml` bind-mounts `dist/`, so a host build is live on :9000. `npm run dev` is the Vite
  dev server.
- Browser tests are Python Playwright journeys in `tests/e2e`. Most mock the API with `page.route`; the `stack`-marked journeys (`test_real_stack.py`, `test_manual_journey.py`) run against a real stack. Vitest uses happy-dom; `npm run test:run` is the one-shot run.
  Give controls accessible names or roles, because tests select by them.
- Never put secrets in the browser. Provider keys stay server-side, and the session is an HttpOnly
  cookie.
