# Mycelium Web Workspace

`web/` is the implementation workspace for the product's web stack.

- `landing/`: Astro public site with Tailwind, MDX, GSAP, React islands, and
  shadcn-compatible primitives.
- `app/`: Next.js dynamic lab app with Tailwind, shadcn/ui, Radix UI, Framer
  Motion, Cytoscape.js, TanStack Query/Table, React Hook Form, and Zod.
- `packages/config/`: shared Mycelium Tailwind v4 theme tokens.
- `backend/`: Django API, orchestration layer, and Celery entrypoint.
- `infra/`: local Nginx and deployment support.

Run commands from the repository root when possible. The root `package.json`
delegates into this workspace so Node install state remains under `web/`.

## Local development (single origin)

`npm run dev` from the repository root starts a dev gateway on port **11050**
alongside Astro, Next.js, and Django. Browse **http://localhost:11050** and use
path-based routing:

| Path | Service |
| --- | --- |
| `/` and public pages | Astro landing (internal `:4321`) |
| `/login`, `/app/*`, `/_next/*` | Next.js app (internal `:3001`) |
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

Landing hero images are copied from `art/` into `landing/public/images/` by
`npm run sync:assets`. That step runs automatically before `npm run dev`,
`npm run dev:landing`, and `npm run build`.
