"""Tests for transactional email (offline, fake transport).

Nothing here touches the network. The Resend client is exercised through a stubbed
``urlopen``, and the templated layer through Django's locmem backend, so the suite
can never send a real message by accident.
"""

from __future__ import annotations

import base64
import json
import urllib.error
from io import BytesIO

import pytest
from django.core import mail as django_mail
from django.core.mail import EmailMessage, EmailMultiAlternatives, send_mail
from django.test import override_settings

from apps.core import mail
from apps.core.mail import client
from apps.core.mail.backend import ResendEmailBackend, _to_payload

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
RESEND = "apps.core.mail.backend.ResendEmailBackend"


# --------------------------------------------------------------------------- #
# Fake transport
# --------------------------------------------------------------------------- #
class FakeResponse(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def resend_calls(monkeypatch):
    """Capture the payloads that would have gone to Resend."""
    calls: list[dict] = []

    def fake_urlopen(request, timeout=None):
        calls.append(json.loads(request.data.decode()))
        return FakeResponse(json.dumps({"id": "msg-1"}).encode())

    monkeypatch.setattr(client.urllib.request, "urlopen", fake_urlopen)
    return calls


def _http_error(status: int, name: str = "", message: str = ""):
    body = json.dumps({"name": name, "message": message}).encode()
    return urllib.error.HTTPError("u", status, name, {}, BytesIO(body))


# --------------------------------------------------------------------------- #
# client
# --------------------------------------------------------------------------- #
@override_settings(RESEND_API_KEY="re_test")
def test_send_returns_the_message_id(resend_calls):
    assert client.send({"to": ["a@example.com"]}).id == "msg-1"
    assert resend_calls == [{"to": ["a@example.com"]}]


@override_settings(RESEND_API_KEY="")
def test_send_without_a_key_is_permanent():
    with pytest.raises(client.ResendError) as exc:
        client.send({})
    assert exc.value.transient is False


@override_settings(RESEND_API_KEY="re_test")
@pytest.mark.parametrize(
    "status,transient",
    [(429, True), (500, True), (503, True), (422, False), (401, False), (403, False)],
)
def test_retryable_statuses_are_marked_transient(monkeypatch, status, transient):
    """A 5xx is worth retrying; an unverified domain will fail the same way forever."""

    def boom(request, timeout=None):
        raise _http_error(status, "some_error", "nope")

    monkeypatch.setattr(client.urllib.request, "urlopen", boom)
    with pytest.raises(client.ResendError) as exc:
        client.send({})
    assert exc.value.status == status
    assert exc.value.transient is transient


@override_settings(RESEND_API_KEY="re_test")
def test_a_transport_failure_is_transient(monkeypatch):
    def boom(request, timeout=None):
        raise urllib.error.URLError("dns")

    monkeypatch.setattr(client.urllib.request, "urlopen", boom)
    with pytest.raises(client.ResendError) as exc:
        client.send({})
    assert (exc.value.status, exc.value.transient) == (0, True)


@override_settings(RESEND_API_KEY="re_test")
def test_a_2xx_without_an_id_is_an_error(monkeypatch):
    monkeypatch.setattr(
        client.urllib.request,
        "urlopen",
        lambda request, timeout=None: FakeResponse(b"{}"),
    )
    with pytest.raises(client.ResendError) as exc:
        client.send({})
    assert exc.value.transient is False


# --------------------------------------------------------------------------- #
# backend adapter
# --------------------------------------------------------------------------- #
def test_payload_carries_both_parts_when_the_message_has_both():
    message = EmailMultiAlternatives("S", "plain body", "from@x.com", ["to@x.com"])
    message.attach_alternative("<p>rich</p>", "text/html")
    payload = _to_payload(message)
    assert payload["text"] == "plain body"
    assert payload["html"] == "<p>rich</p>"


def test_payload_honours_an_html_content_subtype():
    message = EmailMessage("S", "<p>hi</p>", "from@x.com", ["to@x.com"])
    message.content_subtype = "html"
    assert _to_payload(message)["html"] == "<p>hi</p>"
    assert "text" not in _to_payload(message)


def test_payload_carries_cc_bcc_and_reply_to():
    message = EmailMessage(
        "S", "b", "from@x.com", ["to@x.com"],
        cc=["cc@x.com"], bcc=["bcc@x.com"], reply_to=["reply@x.com"],
    )
    payload = _to_payload(message)
    assert payload["cc"] == ["cc@x.com"]
    assert payload["bcc"] == ["bcc@x.com"]
    assert payload["reply_to"] == ["reply@x.com"]


def test_attachments_are_base64_encoded():
    message = EmailMessage("S", "b", "from@x.com", ["to@x.com"])
    message.attach("report.pdf", b"%PDF-bytes", "application/pdf")
    attachment = _to_payload(message)["attachments"][0]
    assert attachment["filename"] == "report.pdf"
    assert base64.b64decode(attachment["content"]) == b"%PDF-bytes"


@override_settings(RESEND_API_KEY="re_test", EMAIL_BACKEND=RESEND)
def test_django_send_mail_reaches_resend(resend_calls):
    """The point of the backend: Django's own senders need no Resend knowledge."""
    assert send_mail("Subject", "Body", "from@x.com", ["to@x.com"]) == 1
    assert resend_calls[0]["subject"] == "Subject"
    assert resend_calls[0]["to"] == ["to@x.com"]


@override_settings(RESEND_API_KEY="re_test")
def test_a_failure_raises_unless_told_otherwise(monkeypatch):
    def boom(request, timeout=None):
        raise _http_error(422, "validation_error", "domain not verified")

    monkeypatch.setattr(client.urllib.request, "urlopen", boom)
    message = EmailMessage("S", "b", "from@x.com", ["to@x.com"])

    with pytest.raises(client.ResendError):
        ResendEmailBackend(fail_silently=False).send_messages([message])
    assert ResendEmailBackend(fail_silently=True).send_messages([message]) == 0


def test_a_message_with_no_recipients_is_skipped():
    message = EmailMessage("S", "b", "from@x.com", [])
    assert ResendEmailBackend().send_messages([message]) == 0


# --------------------------------------------------------------------------- #
# recipients
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "given,expected",
    [
        ("a@example.com", ("a@example.com",)),
        ("  a@example.com  ", ("a@example.com",)),
        (["a@example.com", "a@example.com"], ("a@example.com",)),
        (["a@example.com", "nope", ""], ("a@example.com",)),
        (["nope"], ()),
        (None, ()),
    ],
)
def test_recipients_are_trimmed_deduplicated_and_validated(given, expected):
    assert mail.normalize_recipients(given) == expected


def test_one_bad_address_does_not_cost_the_good_ones():
    """A lab-wide invitation must not be stopped by a single typo."""
    assert mail.normalize_recipients(["good@x.com", "bad", "also@x.com"]) == (
        "good@x.com",
        "also@x.com",
    )


# --------------------------------------------------------------------------- #
# templates
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("template", sorted(mail.TEMPLATES))
def test_every_registered_template_renders_both_parts(template):
    """A missing .txt would ship an HTML-only message; fail here, not in an inbox."""
    html, text = mail.render(template, {"code": "123456", "expires_in": "1 hour"})
    assert html.strip() and text.strip()
    assert "Mycelium" in html


def test_an_unregistered_template_is_refused():
    with pytest.raises(mail.EmailTemplateError):
        mail.render("no_such_template")


def test_a_template_renders_its_link_and_context():
    html, text = mail.render(
        "lab_invitation",
        {
            "lab_name": "Fungal Dynamics Lab",
            "inviter_name": "Ada",
            "invitation_url": "https://example.com/invitations/abc",
        },
    )
    for body in (html, text):
        assert "Fungal Dynamics Lab" in body
        assert "Ada" in body
        assert "https://example.com/invitations/abc" in body


@pytest.mark.parametrize("template", sorted(mail.TEMPLATES))
def test_the_text_part_is_never_html_escaped(template):
    """text/plain renders escapes literally, so "A &amp; B" reaches the reader as-is."""
    _html, text = mail.render(
        template,
        {
            "recipient_name": "Ada <ada@example.com> & co",
            "lab_name": "A & B Lab",
            "department_name": "A & B Department",
            "inviter_name": "A & B",
            "sender": "Mycelium <mycelium@example.com>",
            "code": "123456",
        },
    )
    assert "&lt;" not in text
    assert "&amp;" not in text
    assert "&#x27;" not in text


def test_the_html_part_still_escapes_untrusted_context():
    """The non-escaping engine must not have leaked into the HTML half."""
    html, _text = mail.render("lab_invitation", {"lab_name": "<script>x</script>"})
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_a_verification_code_appears_in_both_parts():
    html, text = mail.render("verification_code", {"code": "824193"})
    assert "824193" in html and "824193" in text


# --------------------------------------------------------------------------- #
# app_url
# --------------------------------------------------------------------------- #
@override_settings(EMAIL_APP_BASE_URL="https://mycelium.example.com")
def test_app_url_builds_an_absolute_link():
    assert mail.app_url("/app/labs") == "https://mycelium.example.com/app/labs"
    assert mail.app_url("app/labs") == "https://mycelium.example.com/app/labs"


@override_settings(EMAIL_APP_BASE_URL="https://mycelium.example.com/")
def test_app_url_does_not_double_the_separator():
    assert mail.app_url("/x") == "https://mycelium.example.com/x"


# --------------------------------------------------------------------------- #
# send_email
# --------------------------------------------------------------------------- #
@override_settings(
    EMAIL_BACKEND=LOCMEM,
    DEFAULT_FROM_EMAIL="Mycelium <mycelium@mail.example.com>",
    EMAIL_REPLY_TO="",
)
def test_send_email_sends_a_multipart_message():
    django_mail.outbox = []
    outcome = mail.send_email(
        "password_reset",
        to="person@example.com",
        context={"reset_url": "https://example.com/r/1", "expires_in": "1 hour"},
    )

    assert outcome.sent is True
    assert outcome.recipients == ("person@example.com",)
    [message] = django_mail.outbox
    assert message.from_email == "Mycelium <mycelium@mail.example.com>"
    assert message.subject == mail.TEMPLATES["password_reset"]
    assert "https://example.com/r/1" in message.body  # the text part
    html, mimetype = message.alternatives[0]
    assert mimetype == "text/html"
    assert "https://example.com/r/1" in html


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_send_email_with_no_valid_recipient_sends_nothing():
    django_mail.outbox = []
    outcome = mail.send_email("test", to=["not-an-address"])
    assert outcome.sent is False
    assert django_mail.outbox == []


@override_settings(EMAIL_BACKEND=LOCMEM, EMAIL_REPLY_TO="support@example.com")
def test_a_configured_reply_to_is_applied():
    django_mail.outbox = []
    mail.send_email("test", to="person@example.com")
    assert django_mail.outbox[0].reply_to == ["support@example.com"]


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_an_explicit_subject_overrides_the_registry():
    django_mail.outbox = []
    mail.send_email("test", to="person@example.com", subject="Custom")
    assert django_mail.outbox[0].subject == "Custom"


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_send_email_carries_attachments():
    django_mail.outbox = []
    mail.send_email(
        "test",
        to="person@example.com",
        attachments=[("report.pdf", b"%PDF", "application/pdf")],
    )
    assert django_mail.outbox[0].attachments[0][0] == "report.pdf"
