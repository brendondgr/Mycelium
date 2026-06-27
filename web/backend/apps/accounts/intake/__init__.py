"""Author-import intake: external author id -> aggregated interest profile draft.

This package lives next to ``Profile`` (brief decision 2) and produces a
*profile draft*, never ``ContentItem`` rows — ingesting papers as content is the
future ``scraper`` app's job. The three source adapters
(:mod:`~apps.accounts.intake.retrievers`) all normalize into one shared shape,
:class:`~apps.accounts.intake.drafts.AuthorProfileDraft`, so they are
interchangeable downstream.
"""

from .drafts import AuthorProfileDraft
from .importer import AuthorImportError, import_author
from .resolve import ResolutionError, ResolvedAuthor, resolve

__all__ = [
    "AuthorProfileDraft",
    "AuthorImportError",
    "import_author",
    "ResolutionError",
    "ResolvedAuthor",
    "resolve",
]
