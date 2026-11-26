"""Proof-neutral lookup sharing and exact support posting index. No new candidate family."""

from collections import Counter, defaultdict


class SupportIndex:
    def __init__(self):
        self.supports = []
        self.by = defaultdict(list)
        self.queries = 0
        self.hits = 0

    def eligible(self, partials, support):
        # append-only IDs survive restore; cache itself is always rebuilt.
        if len(partials) < len(self.supports):
            raise ValueError("SUPPORT_INDEX_POOL_SHRANK")
        for k in range(len(self.supports), len(partials)):
            value = frozenset(partials[k]["support"])
            self.supports.append(value)
            for x in sorted(value):
                self.by[x].append(k)
        counts = Counter()
        for x in sorted(support):
            counts.update(self.by.get(x, ()))
        self.queries += 1
        result = sorted(k for k, c in counts.items() if c == 1)
        self.hits += len(result)
        return result


class CompletionSharing:
    def __init__(self):
        self.positive = {}
        self.misses = {}
        self.lookups = 0
        self.shared_hits = 0
        self.verifications = 0

    def lookup(self, pool, target, child):
        key = (tuple(pool.a.reduce(target)), child)
        if key in self.positive:
            self.shared_hits += 1
            return self.positive[key]
        if self.misses.get(key) == pool.version:
            self.shared_hits += 1
            return None
        self.lookups += 1
        parent = pool.lookup(target, child)
        if parent is None:
            self.misses[key] = pool.version
        else:
            pool.verify_insertion(target, parent, child)
            self.verifications += 1
            self.positive[key] = tuple(parent)
        return parent

    def record(self):
        return dict(
            lookups=self.lookups,
            shared_hits=self.shared_hits,
            verifications=self.verifications,
            positive_targets=len(self.positive),
            negative_policy="POOL_VERSION_ONLY_NOT_A_NONMEMBERSHIP_PROOF",
        )


def continuation_caps(checkpoint, iteration):
    """Add each existing search quantum above retained charges, never reset them."""
    checkpoint = checkpoint or {}
    pool = checkpoint.get("pool", {})
    strong = max(
        [v.get("processed", 0) for v in checkpoint.get("strong", {}).values()] + [0]
    )
    return {
        "word_count": max(
            500000 * iteration, checkpoint.get("stream_words_processed", 0) + 500000
        ),
        "product_tests": max(
            1000000 * iteration, pool.get("product_tests", 0) + 1000000
        ),
        "N_word_count": max(100000 * iteration, strong + 100000),
    }
