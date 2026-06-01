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
