"""The web surface: session auth + CSRF (the app's own), verified email,
audience always the caller alone. Builds the Caller and nothing else: no
permission logic and no prompt logic live in a surface."""

from __future__ import annotations

from ..caller import Audience, Caller, for_thread


def caller(request, thread=None, *, scope=None) -> Caller:
    from apps.accounts.permissions import require_verified_email

    require_verified_email(request.user)
    via = {"session": request.session.session_key or ""}
    if thread is not None:
        return for_thread(thread, surface="web", audience=Audience("person"), via=via)
    from ..caller import Scope

    return Caller(
        user=request.user,
        surface="web",
        scope=scope or Scope(),
        audience=Audience("person"),
        via=via,
    )
