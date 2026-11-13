"""``manage.py llm_check`` on an instance that runs without a model on purpose."""

from io import StringIO

from django.core.management import call_command


def test_no_model_on_purpose_is_not_a_failure(settings):
    settings.LLM_ENABLED = False
    out = StringIO()

    # --strict raises CommandError on any failure; off on purpose is not one.
    call_command("llm_check", "--strict", stdout=out, stderr=StringIO())

    assert "off on purpose" in out.getvalue()
