"""The registry layer: identity and quality, carrying no deadlines at all.

These are not CFP sources. They are what makes the CFP sources usable -- a
canonical venue key to join on, a longevity signal, and a formal quality
assessment. Both are cached locally so the resolve stage never needs the network.
"""

from tools.retrieval.collect.conferences.registry.cache import (
    RegistryCache,
    write_cache,
)

__all__ = ["RegistryCache", "write_cache"]
