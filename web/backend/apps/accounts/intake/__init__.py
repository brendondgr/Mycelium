"""Author-import intake: external author id -> aggregated interest profile draft.

This package lives next to ``Profile`` (brief decision 2) and produces a
*profile draft*, never ``ContentItem`` rows — ingesting papers as content is the
future ``scraper`` app's job. The three source adapters
(:mod:`~apps.accounts.intake.retrievers`) all normalize into one shared shape,
:class:`~apps.accounts.intake.drafts.AuthorProfileDraft`, so they are
interchangeable downstream.
"""

from .agent import IntakeAgent, IntakeState
from .drafts import AuthorProfileDraft
from .extract import extract_profile_fields
from .importer import AuthorImportError, import_author
from .merge import merge_drafts
from .resolve import ResolutionError, ResolvedAuthor, resolve
from .resume import draft_from_resume, extract_text, parse_resume
from .statement import draft_statement
from .synthesize import build_corpus, synthesize_interests

__all__ = [
    "AuthorProfileDraft",
    "AuthorImportError",
    "import_author",
    "IntakeAgent",
    "IntakeState",
    "ResolutionError",
    "ResolvedAuthor",
    "resolve",
    "draft_statement",
    "draft_from_resume",
    "extract_text",
    "extract_profile_fields",
    "parse_resume",
    "merge_drafts",
    "build_corpus",
    "synthesize_interests",
]
