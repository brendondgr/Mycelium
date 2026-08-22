"""Do the two differences `Q-001` names actually hold? (`EXP-2026-08-013` premise check)

`Q-001` asks whether the union pool's advantage survives on the production
corpus, "**where documents are longer and queries are declared interests rather
than keywords**". That clause is an assumption, not a measurement, and the whole
question is shaped by it — so it is measured here rather than repeated.

Two comparisons, both on the same tokenizer the production lexical channel uses
(`apps.content.lexical._TOKEN_RE`), so a token is the same thing on both sides:

1. **Document length** — production `ContentItem` text against LongEval-Sci.
2. **Query length** — the store's declared interests against LongEval topics.

The second bears directly on the cross-encoder refutation: `EXP-2026-08-009` and
`EXP-2026-08-010` found significant *harm* at 1-4 word queries, so how long a
real declared interest is decides whether that finding applies to Mycelium at
all.

Writes `data/premise.json` and `tables/premise.md`. No LLM, no network beyond
the local `ir_datasets` cache.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EXP_DIR.parents[3]
sys.path.insert(0, str(REPO_ROOT / "eval"))
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["DATABASE_URL"] = os.environ.get(
    "MYCELIUM_DATABASE_URL", "postgres://mycelium:mycelium@127.0.0.1:11450/mycelium"
)
os.environ.setdefault("HF_HUB_OFFLINE", "1")

#: How many LongEval documents to sample. The collection is 869,902 documents and
#: the statistic converges long before that; the sample size is recorded so the
#: number is never quoted as if it came from the whole corpus.
LONGEVAL_DOC_SAMPLE = 20_000

BUCKETS = ((1, 2), (3, 4), (5, 99))


def describe(values: list[int]) -> dict:
    values = sorted(values)
    if not values:
        return {}
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 1),
        "median": statistics.median(values),
        "p10": values[len(values) // 10],
        "p90": values[(len(values) * 9) // 10],
    }


def main() -> int:
    import django

    django.setup()
    from apps.content.interests_query import search_interests
    from apps.content.lexical import _TOKEN_RE, _item_text
    from apps.content.models import ContentItem
    from harness import datasets

    out: dict = {"longeval_doc_sample": LONGEVAL_DOC_SAMPLE}

    # --- documents ----------------------------------------------------------
    prod_lengths: dict[str, list[int]] = {}
    for content_type in ("paper", "grant", "conference", "fellowship"):
        prod_lengths[content_type] = [
            len(_TOKEN_RE.findall(_item_text(item).casefold()))
            for item in ContentItem.objects.filter(
                type=content_type, embedding__isnull=False
            ).only("metadata")
        ]
    out["documents"] = {
        f"production:{k}": describe(v) for k, v in prod_lengths.items()
    }

    for cid in ("sci-2026-train", "sci-2025-01"):
        collection = datasets.load_collections()[cid]
        dataset = datasets.load_dataset(collection)
        lengths = [
            len(_TOKEN_RE.findall(_item_text(doc).casefold()))
            for doc in datasets.docs(dataset, limit=LONGEVAL_DOC_SAMPLE)
        ]
        out["documents"][f"longeval:{cid}"] = describe(lengths)

    # --- queries ------------------------------------------------------------
    interests = collect_interests(search_interests)
    out["queries"] = {
        "production:declared_interests": describe([len(i.split()) for i in interests]),
        "production:interest_examples": sorted(interests)[:8],
    }
    for cid, variant in (("sci-2026-train", "dctr"), ("sci-2025-01", "test")):
        collection = datasets.load_collections()[cid]
        dataset = datasets.load_dataset(collection, variant)
        texts = [text for _qid, text in datasets.queries(dataset)]
        out["queries"][f"longeval:{cid}"] = describe([len(t.split()) for t in texts])

    # --- the bucket that matters for the cross-encoder refutation ------------
    out["query_length_buckets"] = {
        "production:declared_interests": bucket_share(
            [len(i.split()) for i in interests]
        ),
    }
    for cid, variant in (("sci-2026-train", "dctr"), ("sci-2025-01", "test")):
        collection = datasets.load_collections()[cid]
        dataset = datasets.load_dataset(collection, variant)
        out["query_length_buckets"][f"longeval:{cid}"] = bucket_share(
            [len(t.split()) for _q, t in datasets.queries(dataset)]
        )

    (EXP_DIR / "data").mkdir(exist_ok=True)
    (EXP_DIR / "data" / "premise.json").write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n"
    )
    write_table(out)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def bucket_share(lengths: list[int]) -> dict[str, float]:
    total = len(lengths) or 1
    return {
        f"{lo}-{hi if hi < 99 else '5+'}": round(
            sum(1 for v in lengths if lo <= v <= hi) / total, 3
        )
        for lo, hi in BUCKETS
    }


def collect_interests(search_interests) -> list[str]:
    from apps.accounts.models import LabProfile, Profile
    from apps.content.models import ProjectProfile

    labels: list[str] = []
    for profile in list(Profile.objects.all()) + list(LabProfile.objects.all()) + list(
        ProjectProfile.objects.all()
    ):
        labels += [i.label for i in search_interests(profile.interests or {})]
    return labels


def write_table(out: dict) -> None:
    lines = [
        "### Document length (tokens, production tokenizer)",
        "",
        "| Corpus | n | mean | median | p10 | p90 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, stats in out["documents"].items():
        if not stats:
            continue
        lines.append(
            f"| `{name}` | {stats['n']:,} | {stats['mean']} | {stats['median']} | "
            f"{stats['p10']} | {stats['p90']} |"
        )
    lines += [
        "",
        "### Query length (words)",
        "",
        "| Query set | n | mean | median | p10 | p90 | 1-2 words | 3-4 | 5+ |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, stats in out["queries"].items():
        if not isinstance(stats, dict) or "n" not in stats:
            continue
        buckets = out["query_length_buckets"].get(name, {})
        lines.append(
            f"| `{name}` | {stats['n']:,} | {stats['mean']} | {stats['median']} | "
            f"{stats['p10']} | {stats['p90']} | "
            + " | ".join(f"{buckets.get(k, 0):.0%}" for k in ("1-2", "3-4", "5-5+"))
            + " |"
        )
    (EXP_DIR / "tables").mkdir(exist_ok=True)
    (EXP_DIR / "tables" / "premise.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
