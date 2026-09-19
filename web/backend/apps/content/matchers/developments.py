"""Does a project development name one of the project's stated things?

Ambient Plan 05, step 10. A development is Mylo's short topic phrase ("the
annotation budget", "graph neural networks"); a stated blocker or method is the
team's own sentence. They name the same thing when most of the development's
content words appear in the stated text — deliberately literal, because a
development that quietly silenced the wrong blocker would hide the one alert
someone needed.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "the a an of for and to in on with our we is was be it this that by at as "
    "from new data".split()
)


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall((text or "").casefold()) if w not in _STOP}


def names(development_topic: str, stated: str) -> bool:
    """True when at least half the topic's content words are in ``stated``."""
    topic = _words(development_topic)
    if not topic:
        return False
    return len(topic & _words(stated)) * 2 >= len(topic)


def any_names(topics, stated: str) -> bool:
    return any(names(topic, stated) for topic in topics)
