# EXP-2026-11-008 — Issues

1. **Dirty tree.** The decision switch (`apps/core/decisions.py`,
   `decision_check`, the `[decision]` config) was uncommitted at run time and
   is committed together with this folder; `code.commit` names the parent.
   Another session's uncommitted `docs/changelog.md` line and related-work
   notes were also present and are not read by anything here.
2. **Run on the host, not in the backend container.** GAIFA's decide binds
   `127.0.0.1` only, so `host.docker.internal:5107` is refused from the
   container. A deployment that runs the nightly in the container needs the
   decision server bound where the container can reach it.
