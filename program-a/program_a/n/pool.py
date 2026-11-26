"""Append-only historical insertion pool, partial-support completion and exact resume."""

from ..contracts import need, digest
from ..shared.weak_verify import inv, expand, Limit
from .legacy.target_pool import TargetPool


class InsertionPool(TargetPool):
    def __init__(self, a, B, G, L):
        super().__init__(a, B, G, L)
        self.tuple_records = []
        self.tuple_keys = set()

    def add(self, x, target, parent, origin):
        a = self.a
        target = a.reduce(target)
        parent = a.reduce(parent)
        f = self.fp(target)
        for k in self.by[x, f]:
            if a.equal(target, self.entries[k]["target"]):
                return
        if len(self.entries) >= self.L["pool_cap"]:
            self.saturation_seen = True
            self.metrics["capacity_rejections"] += 1
            return
        k = len(self.entries)
        self.entries.append(
            {"child": x, "target": target, "parent": parent, "origin": origin}
        )
        self.by[x, f].append(k)
        self.cache[target, x] = parent
        self.change()
        self.metrics["new_isolated"] += 1

    def observe(self, raw, origin="new_word", retain_partial=True):
        a = self.a
        raw = a.reduce(raw)
        root, secs = a.decompose(raw)
        if root == tuple(range(a.d)):
            if (
                raw not in self.tuple_keys
                and len(self.tuple_records) < self.L["tuple_cap"]
            ):
                self.tuple_keys.add(raw)
                self.tuple_records.append(
                    {
                        "parent_word": list(raw),
                        "sections": [list(w) for w in secs],
                        "origin": origin,
                    }
                )
            if all(a.identity(w) for w in secs):
                w = list(expand(raw, self.original))
                if (
                    w
                    and w not in self.identity_relators_basis
                    and len(self.identity_relators_basis) < self.L["relator_cap"]
                ):
                    self.identity_relators_basis.append(w)
        super().observe(raw, origin, retain_partial)

    def export(self):
        z = super().export()
        z["basis_words"] = [list(w) for w in self.B]
        z["original_generator_words"] = [list(w) for w in self.original]
        z["append_only_tuples"] = list(self.tuple_records)
        z["capacity_policy"] = "APPEND_ONLY_NO_EVICTION_NO_RENUMBERING"
        return z

    def restore(self, data):
        need(
            data.get("capacity_policy") == "APPEND_ONLY_NO_EVICTION_NO_RENUMBERING",
            "N_POOL_APPEND_ONLY_POLICY",
        )
        if not (
            len(data["isolated_pairs"]) <= self.L["pool_cap"]
            and len(data.get("partial_tuples", [])) <= self.L["partial_cap"]
            and len(data.get("append_only_tuples", [])) <= self.L["tuple_cap"]
        ):
            raise Limit("RESTORE_CAP_BELOW_RETAINED_DATA")
        for z in data.get("append_only_tuples", []):
            p = tuple(z["parent_word"])
            root, secs = self.a.decompose(p)
            need(
                type(z.get("sections")) is list
                and len(z["sections"]) == self.a.d
                and root == tuple(range(self.a.d))
                and all(self.a.equal(w, v) for w, v in zip(secs, z["sections"])),
                "N_POOL_TUPLE_RESTORE_FALSE",
            )
            if p not in self.tuple_keys:
                self.tuple_keys.add(p)
                self.tuple_records.append(z)
        # Restore saved IDs verbatim. import_saved observes partials and can discover
        # new commutators; reconstruction must never execute that discovery path.
        need(not self.entries and not self.partials, "RESTORE_REQUIRES_EMPTY_POOL")
        need(
            [list(w) for w in self.B] == data["basis_words"]
            and [list(w) for w in self.original] == data["original_generator_words"],
            "RESTORE_POOL_BASIS_CHANGED",
        )
        for old in data["isolated_pairs"]:
            x = old["child"]
            need(type(x) is int and 0 <= x < self.a.d, "RESTORE_ISOLATED_CHILD")
            target = self.a.reduce(old["target_word"])
            parent = self.a.reduce(old["parent_word"])
            self.verify_insertion(target, parent, x)
            k = len(self.entries)
            self.entries.append(
                {
                    "child": x,
                    "target": target,
                    "parent": parent,
                    "origin": old.get("origin", "UNKNOWN_HISTORICAL_ORIGIN"),
                }
            )
            self.by[x, self.fp(target)].append(k)
            self.cache[target, x] = parent
        for z in data["projection_lifts"]:
            x, i = z["child"], z["basis_generator"]
            need(
                0 <= x < self.a.d and 1 <= i <= len(self.B), "RESTORE_PROJECTION_INDEX"
            )
            parent = tuple(z["parent_word"])
            root, secs = self.a.decompose(parent)
            need(
                root[x] == x and self.a.equal(secs[x], self.B[i - 1]),
                "RESTORE_PROJECTION_FALSE",
            )
            self.projection[x, i] = parent
        self.trans = {}
        for z in data["root_transports"]:
            x = z["target_child"]
            p = tuple(z["parent_word"])
            need(
                0 <= x < self.a.d and self.a.root(p)[0] == x, "RESTORE_TRANSPORT_FALSE"
            )
            self.trans[x] = p
        relators = data.get("identity_relators_basis", [])
        need(len(relators) <= self.L["relator_cap"], "RESTORE_RELATOR_CAP")
        for w in relators:
            need(self.a.identity(expand(w, self.B)), "RESTORE_RELATOR_FALSE")
        self.identity_relators_basis = [list(w) for w in relators]
        for z in data.get("partial_tuples", []):
            raw = tuple(z["parent_word"])
            root, secs = self.a.decompose(raw)
            support = frozenset(x for x, v in enumerate(secs) if not self.a.identity(v))
            need(
                root == tuple(range(self.a.d))
                and sorted(support) == z["support"]
                and len(support) > 1,
                "RESTORE_PARTIAL_FALSE",
            )
            need(raw not in self.partial_seen, "RESTORE_PARTIAL_DUPLICATE")
            k = len(self.partials)
            self.partials.append({"parent": raw, "sections": secs, "support": support})
            self.partial_seen.add(raw)
            for x in range(self.a.d):
                self.partial_by[
                    x, tuple(self.fp(secs[y]) for y in range(self.a.d) if y != x)
                ].append(k)
        need(
            len(self.entries) == len(data["isolated_pairs"]),
            "RESTORE_RENUMBERED_ISOLATED_POOL",
        )
        for z, old in zip(self.entries, data["isolated_pairs"]):
            need(
                z["child"] == old["child"]
                and self.a.equal(z["target"], old["target_word"])
                and self.a.equal(z["parent"], old["parent_word"]),
                "RESTORE_ISOLATED_ORDER_CHANGED",
            )
        # Preserve cumulative discovery charges and version exactly; caches are rebuilt.
        self.version = data["pool_version"]
        self.product_tests = data.get("product_tests", 0)
        self.metrics.update(data.get("metrics", {}))
        self.imported.update(data.get("imported_exact_checks", {}))

    def checkpoint(self):
        z = self.export()
        z["product_tests"] = self.product_tests
        return z
