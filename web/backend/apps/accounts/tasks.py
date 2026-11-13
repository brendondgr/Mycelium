"""Background work for accounts."""

from __future__ import annotations

from celery import shared_task


@shared_task(name="apps.accounts.send_password_reset", ignore_result=True)
def send_password_reset(email: str) -> None:
    """Look the address up and mail a reset link if it is an account's.

    Run off the request on purpose: done inline, a registered address cost a
    mail-provider round trip that an unknown one did not, and the response time
    told a prober which addresses have accounts. See
    :func:`apps.accounts.password_reset.request_reset_later`.
    """
    from .password_reset import request_reset

    request_reset(email)
