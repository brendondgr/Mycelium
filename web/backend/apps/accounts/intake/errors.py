"""Shared intake errors (kept separate to avoid import cycles)."""

from __future__ import annotations


class AuthorImportError(RuntimeError):
    """Raised when an author cannot be imported from its source."""
