# Frontend — React/Vite studio

- `src/main.tsx` mounts `<AuthGate><App/></AuthGate>`. `SignIn.tsx` asks for `API__TOKEN` when the
  API requires it, and a 401 from `api.ts` re-locks the app.
- `src/App.tsx` routes by `window.location.pathname`. The pages are the vault, `Workspace`,
  `ArtifactStudio`, `KnowledgeGraph`, `WritersRoom` (`/projects/<id>/room`: room workflows, runs,
  proposal review, usefulness) and `ProviderSettings`.
- `src/api.ts` is the typed fetch client. Every call goes through `request()`, which sends
  same-origin credentials and turns API errors into `ApiError(status, detail)`.
- Styles are plain CSS in `src/*.css`. Static assets and favicons live in `public/`.
- Build with `npm run build` (runs `tsc --noEmit`, then Vite). The web process serves `dist/`.
  `compose.dev.yml` bind-mounts `dist/`, so a host build is live on :9000. `npm run dev` is the Vite
  dev server.
- Browser tests are Python Playwright journeys in `tests/e2e`, which mock the API with `page.route`.
  Give controls accessible names or roles, because tests select by them.
- Never put secrets in the browser. Provider keys stay server-side, and the session is an HttpOnly
  cookie.
