# Mycelium Web Workspace

`web/` is the implementation workspace for the product's web stack.

- `landing/`: Astro public site with Tailwind and MDX. It ships **zero framework
  JavaScript** — React components are server-rendered only and interactivity is
  CSS (`:has()`, `:checked`, `animation-timeline: view()`). Adding a `client:*`
  directive would start shipping React.
- `app/`: Next.js App Router lab workspace with Tailwind, Radix UI, TanStack
  Query/Table, React Hook Form, and Zod.
- `packages/config/`: shared Mycelium Tailwind v4 theme tokens.
- `backend/`: Django API, orchestration layer, and Celery entrypoint.
- `art/`: Mylo and hero artwork masters.
- `scripts/`: dev gateway and the art-sync step.
- `infra/`: local Nginx config.

Run commands from the repository root when possible. The root `package.json`
delegates into this workspace so Node install state remains under `web/`.

## Local development (single origin)

`npm run dev` from the repository root starts a dev gateway on port **11050**
alongside Astro, Next.js, and Django. Browse **http://localhost:11050** and use
path-based routing:

| Path | Service |
| --- | --- |
| `/` and public pages | Astro landing (internal `:4321`) |
| `/login`, `/signup`, `/app/*`, `/_next/*` | Next.js app (internal `:3001`) |
| `/api/*`, `/admin/*` | Django (internal `:8000`) |

Direct ports remain available for focused debugging (`:4321`, `:3001`, `:8000`).

## Docker (single origin)

`docker compose up` from the repository root exposes the same path map through
Nginx at **http://localhost:11050**. Host-published ports follow the
`11050 + 100·n` scheme (landing `:11150`, app `:11250`, Django `:11350`,
Postgres `:11450`, Redis `:11550`, Neo4j `:11650`/`:11750`, MinIO
`:11850`/`:11950`).

If workspace packages fail to resolve inside containers after a host-side
`npm install`, reset Docker volumes:

```sh
docker compose down -v
docker compose up
```

Artwork masters in `art/` are resized to WebP derivatives by
`scripts/sync-art-assets.mjs` (`npm run sync:assets`), which runs automatically
on every workspace's `predev` / `prebuild`. Landing derivatives go to
`landing/public/images/`; **app derivatives go to `app/public/` root**, not a
subdirectory, because the gateway only proxies single-segment root static files
to the app. All derivatives are git-ignored — edit the master and re-run the
sync.
