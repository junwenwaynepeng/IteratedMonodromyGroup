"""Actual N-word parent search, independent of the first weak parent representation.

For a faithful tree action a supported tuple has a unique parent group element.
Thus two correct parents cannot be respectively outside and inside N. What can
fail is membership *proof* for the first spelling; a later N-word spelling must
remain discoverable. This module stores that proof separately and resumes its
own N-alphabet cursor.
"""

from ..contracts import need
from ..shared.weak_verify import inv
from ..shared.exact import expand
from .legacy.streaming import words


class StrongSearch:
    def __init__(self, candidate, a, G, L, state=None):
        self.candidate, self.a, self.G, self.L = candidate, a, G, L
        self.cursor = 0
        self.processed = 0
        self.found = {}
        if state:
            need(
                state["candidate_key"] == candidate.key,
                "STRONG_CANDIDATE_ALPHABET_CHANGED",
            )
            self.cursor = state["word_cursor"]
            self.processed = state["words_processed"]
            for row in state["found"]:
                i, x = row["N_generator"], row["child"]
                nw = tuple(row["parent_N_word"])
                p = expand(nw, candidate.cover.N, L["export_word_length"])
                self.accept(i, x, p, nw)

    def accept(self, i, x, p, nw):
        N = self.candidate.cover.N
        need(1 <= i <= len(N) and 0 <= x < self.a.d, "STRONG_TARGET")
        need(
            self.a.equal(p, expand(nw, N, self.L["export_word_length"])),
            "STRONG_PARENT_N_PROOF_FALSE",
        )
        for y in range(self.a.d):
            out, s = self.a.step(p, y)
            need(
                out == y and self.a.equal(s, N[i - 1] if y == x else ()),
                "STRONG_SUPPORTED_PARENT_FALSE",
            )
        self.found.setdefault(
            (i, x), {"parent_word": tuple(p), "parent_N_word": tuple(nw)}
        )

    def reuse_weak_proofs(self, found):
        for (i, x), p in found.items():
            if (i, x) in self.found:
                continue
            try:
                nw = self.candidate.cover.rewrite(
                    expand(p, self.G, self.L["export_word_length"])
                )
            except ValueError:
                continue
            self.accept(i, x, p, nw)

    def step(self, pool, count):
        N = self.candidate.cover.N
        if not N:
            return
        left = min(count, max(0, self.L["N_word_count"] - self.processed))
        for index, nw in words(
            len(N), self.L["N_word_depth"], left, self.cursor, False
        ):
            p = expand(nw, N, self.L["export_word_length"])
            pool.observe(p, "new_N_word_parent")
            root, secs = self.a.decompose(p)
            if root == tuple(range(self.a.d)):
                for x, s in enumerate(secs):
                    if all(self.a.identity(v) for y, v in enumerate(secs) if y != x):
                        for i, n in enumerate(N, 1):
                            if (
                                (i, x) not in self.found
                                and self.a.fingerprint(s, pool.depth)
                                == self.a.fingerprint(n, pool.depth)
                                and self.a.equal(s, n)
                            ):
                                self.accept(i, x, p, nw)
            self.cursor = index + 1
            self.processed += 1

    def snapshot(self):
        return {
            "candidate_key": self.candidate.key,
            "word_cursor": self.cursor,
            "words_processed": self.processed,
            "found": [
                {
                    "N_generator": i,
                    "child": x,
                    "parent_word": list(z["parent_word"]),
                    "parent_N_word": list(z["parent_N_word"]),
                }
                for (i, x), z in sorted(self.found.items())
            ],
            "unmet": [
                {"N_generator": i, "child": x}
                for i in range(1, len(self.candidate.cover.N) + 1)
                for x in range(self.a.d)
                if (i, x) not in self.found
            ],
        }
