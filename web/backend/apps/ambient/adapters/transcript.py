"""Meeting transcripts (Plan 11) — one meeting is one window.

A transcript's speakers are labels ("Ada", "Speaker 2"). The person uploading
it maps the labels to members of the meeting's lab or project, and the
ingest step hands the adapter ``"user:<pk>"`` for a mapped turn. A turn nobody
mapped never reaches the adapter. Resolution is the account itself, active
or not at all.
"""

from __future__ import annotations

from django.contrib.auth.models import User

from ..models import Platform, Source
from .base import Adapter


class TranscriptAdapter(Adapter):
    platform = Platform.TRANSCRIPT
    source_kind = Source.Kind.TRANSCRIPT

    def resolve_speaker(self, author_external_id: str) -> User | None:
        prefix, _, pk = str(author_external_id).partition(":")
        if prefix != "user" or not pk.isdigit():
            return None
        return User.objects.filter(pk=int(pk), is_active=True).first()
