"""Source normalizers: raw payload -> AuthorProfileDraft.

Every normalizer returns the exact same :class:`AuthorProfileDraft` fields —
that parity is what makes the three sources interchangeable downstream. These
are pure functions over canned dicts, so they are fully unit-tested offline.
"""
