"""Shared exact-witness pool, bounded partial tuples and versioned misses."""

from collections import defaultdict, Counter
from ...shared.weak_verify import inv, expand, Limit
from . import pool as legacy
from ..optimizations import SupportIndex


class TargetPool(legacy.Pool):
    def __init__(self, a, B, original, L):
        super().__init__(a, B, original, L)
        self.version = 0
        self.misses = {}
        self.partials = []
        self.partial_by = defaultdict(list)
        self.partial_seen = set()
        self.targets = defaultdict(set)
        self.metrics = Counter()
        self.imported = Counter()
        self.saturation_seen = False
        self.support_index = SupportIndex()

    def change(self):
        self.version += 1

    def set_targets(self, targets):
        for x, w in targets:
            self.targets[x, self.fp(w)].add(self.a.reduce(w))

    def is_target(self, x, w):
        return any(self.a.equal(w, t) for t in self.targets.get((x, self.fp(w)), ()))

    def add(self, x, target, parent, origin):
        a = self.a
        target = a.reduce(target)
        parent = a.reduce(parent)
        f = self.fp(target)
        for k in self.by[x, f]:
            self.metrics["bucket_exact_checks"] += 1
            z = self.entries[k]
            if a.equal(target, z["target"]):
                if len(parent) < len(z["parent"]):
                    z["parent"] = parent
                    self.change()
                    self.metrics["shorter_witnesses"] += 1
                return
        if len(self.entries) >= self.L["pool_cap"]:
            self.saturation_seen = True
            if not self.is_target(x, target):
                self.metrics["capacity_rejections"] += 1
                return
            options = [
                (len(z["parent"]), k)
                for k, z in enumerate(self.entries)
                if not self.is_target(z["child"], z["target"])
            ]
            if not options:
                self.metrics["capacity_rejections"] += 1
                return
            _, k = max(options)
            self.entries[k] = {
                "child": x,
                "target": target,
                "parent": parent,
                "origin": origin,
            }
            self.by = defaultdict(list)
            for j, z in enumerate(self.entries):
                self.by[z["child"], self.fp(z["target"])].append(j)
            self.metrics["target_aware_replacements"] += 1
        else:
            k = len(self.entries)
            self.entries.append(
                {"child": x, "target": target, "parent": parent, "origin": origin}
            )
            self.by[x, f].append(k)
        self.cache[target, x] = parent
        self.change()
        self.metrics["new_isolated"] += 1

    def lookup(self, target, x):
        self.a.tick()
        key = (self.a.reduce(target), x)
        if key in self.cache:
            self.metrics["successful_lookup_cache_hits"] += 1
            return self.cache[key]
        if self.misses.get(key) == self.version:
            self.metrics["versioned_miss_cache_hits"] += 1
            return None
        result = super().lookup(target, x)
        if result is None:
            self.misses[key] = self.version
        else:
            self.cache[key] = result
        return result

    def verify_insertion(self, target, parent, x):
        a = self.a
        root, secs = a.decompose(parent)
        assert root == tuple(range(a.d)), "Imported parent does not fix root"
        for y, s in enumerate(secs):
            assert a.equal(
                s, target if y == x else ()
            ), "Imported supported section mismatch"

    def import_saved(self, data):
        a = self.a
        assert [list(w) for w in self.B] == data["basis_words"] and [
            list(w) for w in self.original
        ] == data["original_generator_words"], "Saved pool basis mismatch"
        for z in data["isolated_pairs"]:
            x = z["child"]
            assert 0 <= x < a.d
            self.verify_insertion(z["target_word"], z["parent_word"], x)
            self.add(x, z["target_word"], z["parent_word"], "EXACT_REPLAY_IMPORTED")
            self.imported["isolated"] += 1
        for z in data["projection_lifts"]:
            x, i = z["child"], z["basis_generator"]
            assert 0 <= x < a.d and 1 <= i <= len(self.B)
            root, secs = a.decompose(z["parent_word"])
            assert root[x] == x and a.equal(
                secs[x], self.B[i - 1]
            ), "Imported projection mismatch"
            self.projection[x, i] = tuple(z["parent_word"])
            self.imported["projection"] += 1
            self.change()
        for z in data["root_transports"]:
            x = z["target_child"]
            assert (
                0 <= x < a.d and a.root(z["parent_word"])[0] == x
            ), "Imported root transport mismatch"
            self.trans[x] = tuple(z["parent_word"])
            self.imported["transport"] += 1
            self.change()
        for w in data.get("identity_relators_basis", []):
            assert a.identity(expand(w, self.B)), "Imported relator mismatch"
        self.identity_relators_basis = [
            list(w) for w in data.get("identity_relators_basis", [])
        ][: self.L["relator_cap"]]
        for z in data.get("partial_tuples", []):
            self.observe(z["parent_word"], "IMPORTED_PARTIAL")

    def observe(self, raw, origin="new_word", retain_partial=True):
        a = self.a
        raw = a.reduce(raw)
        root, secs = a.decompose(raw)
        if root[0] not in self.trans:
            self.trans[root[0]] = raw
            self.change()
        for x, s in enumerate(secs):
            if root[x] != x:
                continue
            f = self.fp(s)
            for i, b in enumerate(self.B, 1):
                if (x, i) not in self.projection and f == self.fp(b) and a.equal(s, b):
                    self.projection[x, i] = raw
                    self.change()
        if root != tuple(range(a.d)):
            return
        support = frozenset(x for x, s in enumerate(secs) if not a.identity(s))
        if len(support) == 1:
            x = next(iter(support))
            self.add(x, secs[x], raw, origin)
            self.add(x, inv(secs[x]), inv(raw), origin + "_inverse")
            return
        if not support:
            return
        if (
            not retain_partial
            or raw in self.partial_seen
            or len(self.partials) >= self.L["partial_cap"]
        ):
            return
        # All selected parents fix the root; child sections multiply componentwise.
        new = {"parent": raw, "sections": secs, "support": support}
        self.partial_seen.add(raw)
        relevant = self.support_index.eligible(self.partials, support)
        self.metrics["partial_support_rows_avoided"] += len(self.partials) - len(
            relevant
        )
        for old_id in relevant:
            old = self.partials[old_id]
            if self.metrics["partial_pair_tests"] >= self.L["partial_pair_tests"]:
                break
            common = support & old["support"]
            if len(common) == 1:
                self.metrics["partial_pair_tests"] += 1
                self.metrics["support_commutators"] += 1
                p = a.reduce(old["parent"] + raw + inv(old["parent"]) + inv(raw))
                self.observe(p, "partial_support_commutator", False)
        for x in range(a.d):
            key = tuple(self.fp(inv(secs[y])) for y in range(a.d) if y != x)
            for k in self.partial_by[x, key][: self.L["partial_bucket_cap"]]:
                if self.metrics["partial_pair_tests"] >= self.L["partial_pair_tests"]:
                    break
                old = self.partials[k]
                self.metrics["partial_pair_tests"] += 1
                if all(
                    a.identity(old["sections"][y] + secs[y])
                    for y in range(a.d)
                    if y != x
                ):
                    self.observe(
                        a.reduce(old["parent"] + raw),
                        "partial_outside_cancellation",
                        False,
                    )
                    self.metrics["exact_partial_cancellations"] += 1
        k = len(self.partials)
        self.partials.append(new)
        for x in range(a.d):
            self.partial_by[
                x, tuple(self.fp(secs[y]) for y in range(a.d) if y != x)
            ].append(k)

    def saturated(self):
        return (
            len(self.entries) >= self.L["pool_cap"]
            and len(self.projection) == self.a.d * len(self.B)
            and len(self.trans) == self.a.d
            and len(self.partials) >= self.L["partial_cap"]
        )

    def export(self):
        r = super().export()
        r.update(
            partial_tuples=[
                {"parent_word": list(z["parent"]), "support": sorted(z["support"])}
                for z in self.partials
            ],
            pool_version=self.version,
            metrics=dict(self.metrics),
            imported_exact_checks=dict(self.imported),
        )
        return r
