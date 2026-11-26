"""Bounded weak supported-image discovery on a supplied exact transition model.
One shared isolated-section word pool; every accepted finite package is replayed.
No expected I-values, map formula or historic N/lift dictionaries are consulted.
"""

import json, time, argparse
from collections import defaultdict
from ...shared.weak_verify import (
    Action,
    Limit,
    expand,
    inv,
    verify_subgroup_certificate,
)
from . import cover_tools as tools
from ...shared.weak_image import verify_supported_image_certificate

DEFAULT = {
    **tools.DEFAULT,
    "seconds": 30,
    "identity_states": 8000,
    "word_count": 100000,
    "word_depth": 12,
    "coset_cap": 256,
    "pool_cap": 600,
    "product_tests": 60000,
    "universal_moduli": [2, 3, 4],
    "fingerprint_depth": 3,
    "candidate_N_cap": 150,
    "torsion_order_cap": 12,
    "mixed_cover_cap": 4,
    "relator_cap": 200,
}


class Pool:
    def __init__(self, a, B, original, L):
        self.a = a
        self.B = B
        self.original = original
        self.L = L
        self.entries = []
        self.by = defaultdict(list)
        self.projection = {}
        self.trans = {0: ()}
        self.count = 0
        self.product_tests = 0
        self.identity_relators_basis = []
        self.cache = {}
        self.depth = L["fingerprint_depth"]
        while a.d**self.depth > 64:
            self.depth -= 1

    def fp(self, w):
        return self.a.fingerprint(w, self.depth)

    def add(self, x, target, parent, origin):
        if len(self.entries) >= self.L["pool_cap"]:
            return
        target = self.a.reduce(target)
        parent = self.a.reduce(parent)
        f = self.fp(target)
        for k in self.by[x, f]:
            if self.a.equal(target, self.entries[k]["target"]):
                return
        k = len(self.entries)
        self.entries.append(
            {"child": x, "target": target, "parent": parent, "origin": origin}
        )
        self.by[x, f].append(k)

    def search(self, progress):
        a = self.a
        B = self.B
        basisfps = {i: self.fp(w) for i, w in enumerate(B, 1)}
        invol = all(a.identity(b + b) for b in B)
        for w in tools.words(len(B), self.L["word_depth"], self.L["word_count"], invol):
            a.tick()
            self.count += 1
            raw = expand(w, B)
            root = a.root(raw)
            if root[0] not in self.trans:
                self.trans[root[0]] = raw
            if self.count % 100 == 1:
                progress.update(self.stats())
            secs = [a.step(raw, x)[1] for x in range(a.d)]
            for x, s in enumerate(secs):
                if root[x] != x:
                    continue
                f = self.fp(s)
                for i, b in enumerate(B, 1):
                    if (
                        (x, i) not in self.projection
                        and f == basisfps[i]
                        and a.equal(s, b)
                    ):
                        self.projection[x, i] = raw
            if root != tuple(range(a.d)):
                continue
            nonzero = [x for x, s in enumerate(secs) if not a.identity(s)]
            if (
                not nonzero
                and w
                and len(self.identity_relators_basis) < self.L["relator_cap"]
            ):
                self.identity_relators_basis.append(list(w))
            if len(nonzero) == 1:
                x = nonzero[0]
                self.add(x, secs[x], raw, "shared_word_ball")
                self.add(x, inv(secs[x]), inv(raw), "inverse_of_shared_word_ball")
        progress.update(self.stats())

    def export(self):
        return {
            "scope": "LOCAL ONLY; exact witnesses and true identity relators, not an adaptive subgroup certificate",
            "basis_words": self.B,
            "original_generator_words": self.original,
            "isolated_pairs": [
                {
                    "child": z["child"],
                    "target_word": z["target"],
                    "parent_word": z["parent"],
                    "origin": z["origin"],
                }
                for z in self.entries
            ],
            "projection_lifts": [
                {
                    "child": x,
                    "basis_generator": i,
                    "parent_word": p,
                    "scope": "parent fixes this child; other root outputs may permute",
                }
                for (x, i), p in sorted(self.projection.items())
            ],
            "root_transports": [
                {"target_child": x, "parent_word": p}
                for x, p in sorted(self.trans.items())
            ],
            "identity_relators_basis": self.identity_relators_basis,
        }

    def stats(self):
        return {
            "searched_words": self.count,
            "isolated_pool_entries": len(self.entries),
            "projection_lifts_found": len(self.projection),
            "projection_lifts_required": self.a.d * len(self.B),
            "root_transports_found": len(self.trans),
            "product_filter_tests": self.product_tests,
        }

    def direct(self, target, x):
        a = self.a
        target = a.reduce(target)
        key = (target, x)
        if key in self.cache:
            return self.cache[key]
        if a.identity(target):
            self.cache[key] = ()
            return ()
        f = self.fp(target)
        for k in self.by[x, f]:
            z = self.entries[k]
            if a.equal(z["target"], target):
                self.cache[key] = z["parent"]
                return z["parent"]
        # Meet-in-the-middle product of two supported elements. Permutations filter only.
        entries = [z for z in self.entries if z["child"] == x]
        for u in entries:
            a.tick()
            self.product_tests += 1
            if self.product_tests > self.L["product_tests"]:
                break
            fu = self.fp(u["target"])
            ipu = [0] * len(fu)
            for i, j in enumerate(fu):
                ipu[j] = i
            need = tuple(f[ipu[j]] for j in range(len(f)))
            for k in self.by[x, need]:
                v = self.entries[k]
                if a.equal(u["target"] + v["target"], target):
                    p = a.reduce(u["parent"] + v["parent"])
                    self.cache[key] = p
                    return p
        return None

    def project(self, raw, x):
        basis = expand(raw, self.original)
        out = ()
        for g in basis:
            p = self.projection.get((x, abs(g)))
            if p is None:
                return None
            out += p if g > 0 else inv(p)
        return self.a.reduce(out)

    def lookup(self, target, x):
        p = self.direct(target, x)
        if p is not None:
            return p
        # A parent at another child can be transported using a root word, with the
        # exact section conjugation corrected by a root-stabilizer projection lift.
        if x == 0:
            for y, t in self.trans.items():
                if y == 0:
                    continue
                q = self.direct(target, y)
                if q is None:
                    continue
                u = self.a.step(t, 0)[1]
                lu = self.project(u, 0)
                if lu is None:
                    continue
                p = self.a.reduce(inv(lu) + t + q + inv(t) + lu)
                self.cache[self.a.reduce(target), 0] = p
                return p
        elif x in self.trans:
            q = self.lookup(target, 0)
            if q is None:
                return None
            t = self.trans[x]
            u = self.a.step(t, 0)[1]
            lu = self.project(u, 0)
            if lu is None:
                return None
            p = self.a.reduce(inv(t) + lu + q + inv(lu) + t)
            self.cache[self.a.reduce(target), x] = p
            return p
        return None

    def mod2_completion(self, C):
        # Squares and positive basic commutators normally generate the free mod2 kernel.
        primitive = {("square", i): (i, i) for i in range(1, len(self.B) + 1)}
        primitive.update(
            {
                ("comm", i, j): (i, j, -i, -j)
                for i in range(1, len(self.B) + 1)
                for j in range(i + 1, len(self.B) + 1)
            }
        )
        found = {}
        missing = []
        for key, target in primitive.items():
            p = self.lookup(expand(target, self.B), 0)
            if p is None:
                missing.append(list(key))
            else:
                found[key] = p
        if missing:
            return {}, {"missing_mod2_primitives": missing}
        out = {}
        for i, n in enumerate(C.Nbasis, 1):
            p = ()
            for prefix, key, sign in tools.collect_mod2(n):
                t = self.project(expand(prefix, self.B), 0)
                if t is None:
                    return {}, {"missing_projection_at_child0": True}
                v = found[key]
                p += t + (v if sign > 0 else inv(v)) + inv(t)
            p = self.a.reduce(p)
            for x in range(self.a.d):
                if x == 0:
                    out[i, x] = p
                    continue
                if x not in self.trans:
                    continue
                t = self.trans[x]
                lu = self.project(self.a.step(t, 0)[1], 0)
                if lu is None:
                    continue
                out[i, x] = self.a.reduce(inv(t) + lu + p + inv(lu) + t)
        return out, {"missing_mod2_primitives": []}


def run_case(packet, limits=None, basis_hint=None):
    L = dict(DEFAULT)
    L.update(limits or {})
    start = time.monotonic()
    end = start + L["seconds"]
    ans = {
        "schema_version": 1,
        "status": "NO_WEAK_CERT_WITHIN_LIMIT",
        "map_id": packet.get("map_id"),
        "limits": L,
        "candidates": [],
        "certificates": [],
        "diagnostics": {},
        "scope": "supplied stored action; weak supported image only; no geometric/exact-I/universal-termination claim",
    }
    try:
        a = Action(packet, L)
        B = original = None
        if basis_hint:
            hint = basis_hint.get("diagnostics", basis_hint)
            hint = hint.get("certificate", hint)
            try:
                bh = hint["basis_words"]
                oh = hint["original_generator_words"]
                assert len(oh) == a.q and bh
                for g, w in enumerate(oh, 1):
                    assert a.equal(expand(w, bh), (g,))
                B = [tuple(w) for w in bh]
                original = [tuple(w) for w in oh]
                ans["diagnostics"]["basis_hint"] = "EXACTLY_REPLAYED"
            except Limit:
                raise
            except Exception as e:
                ans["diagnostics"]["basis_hint"] = "REJECTED " + repr(e)
        if B is None:
            a.deadline = min(end, start + L["seconds"] * 0.2)
            B, original, pairs = tools.find_basis(a, L)
            ans["diagnostics"]["basis_pair_tests"] = pairs
        ans["diagnostics"].update(
            {
                "basis_words": B,
                "original_generator_words": original,
                "basis_size": len(B),
            }
        )
        orders = []
        a.deadline = min(end, start + L["seconds"] * 0.27)
        for b in B:
            order = None
            try:
                for n in range(1, L["torsion_order_cap"] + 1):
                    if a.identity(b * n):
                        order = n
                        break
            except Limit:
                pass
            orders.append(order)
        ans["diagnostics"]["proved_basis_orders"] = orders
        moduli = list(
            dict.fromkeys(
                list(L["universal_moduli"]) + [a.d] + [o for o in orders if o and o > 1]
            )
        )
        kinds = ["root_sign_kernel", "root_kernel"] + [
            "universal_mod_" + str(m)
            for m in moduli
            if m > 1 and m ** len(B) <= L["coset_cap"]
        ]
        mixed = []
        preferred = tuple(o if o and o > 1 else 2 for o in orders)
        if len(set(preferred)) > 1:
            mixed.append(preferred)
        for n in (2, 3):
            v = tuple(o if o and o > 1 else n for o in orders)
            if len(set(v)) > 1 and v not in mixed:
                mixed.append(v)
        for v in mixed[: L["mixed_cover_cap"]]:
            product = 1
            for n in v:
                product *= n
            if product <= L["coset_cap"]:
                kinds.append("universal_mixed_" + "_".join(map(str, v)))
        covers = []
        for j, kind in enumerate(kinds):
            row = {"candidate_type": kind, "status": "NO_WEAK_CERT_WITHIN_LIMIT"}
            ans["candidates"].append(row)
            try:
                a.deadline = min(
                    end,
                    time.monotonic()
                    + max(
                        0.01,
                        (start + L["seconds"] * 0.35 - time.monotonic())
                        / (len(kinds) - j),
                    ),
                )
                C = tools.Cover(a, B, kind, L["coset_cap"])
                row.update(
                    {
                        "N_generator_count": len(C.N),
                        "cover_upper_bound": len(C.reps),
                        "N_generators": C.N,
                        "exact_quotient_status": "NOT_INFERRED_FROM_COVER",
                    }
                )
                if len(C.N) > L["candidate_N_cap"]:
                    row["limit_reached"] = "candidate_N_cap"
                    continue
                cert = C.certificate(original)
                partial = verify_subgroup_certificate(
                    packet,
                    cert,
                    {**L, "seconds": max(0.01, a.deadline - time.monotonic())},
                )
                row["subgroup_verification"] = partial
                row["finite_index_status"] = (
                    "CERTIFIED_UPPER_BOUND"
                    if partial["status"] == "PASS_SUBGROUP_DATA"
                    else partial["status"]
                )
                row["normality_status"] = (
                    "PASS"
                    if partial["status"] == "PASS_SUBGROUP_DATA"
                    else partial["status"]
                )
                covers.append((C, cert, row))
            except Limit as e:
                row["limit_reached"] = str(e)
            except Exception as e:
                row.update({"status": "ERROR", "error": repr(e)})
        pool = Pool(a, B, original, L)
        pool.identity_relators_basis = [[i] * o for i, o in enumerate(orders, 1) if o][
            : L["relator_cap"]
        ]
        ans["diagnostics"]["shared_pool"] = {}
        a.deadline = min(end, start + L["seconds"] * 0.75)
        try:
            pool.search(ans["diagnostics"]["shared_pool"])
        except Limit as e:
            ans["diagnostics"]["pool_limit_reached"] = str(e)
        for j, (C, cert, row) in enumerate(covers):
            a.deadline = min(
                end,
                time.monotonic()
                + max(0.01, (end - time.monotonic()) / (len(covers) - j)),
            )
            targets = []
            lifts = []
            complete = {}
            completion = {}
            try:
                # First reuse all isolated entries/products across every candidate N.
                for i, n in enumerate(C.N, 1):
                    for x in range(a.d):
                        p = pool.lookup(n, x)
                        if p is not None:
                            complete[i, x] = p
                if C.kind == "universal_mod_2" and len(complete) < len(C.N) * a.d:
                    more, completion = pool.mod2_completion(C)
                    complete.update(more)
                for i, n in enumerate(C.N, 1):
                    for x in range(a.d):
                        p = complete.get((i, x))
                        t = {
                            "N_generator": i,
                            "child": x,
                            "found": p is not None,
                            "parent_N_membership": "UNKNOWN",
                        }
                        if p is not None:
                            t["parent_length"] = len(p)
                            lifts.append(
                                {"N_generator": i, "child": x, "parent_word": p}
                            )
                            try:
                                nw = C.rewrite(expand(p, original))
                                if a.equal(expand(nw, C.N), p):
                                    t.update(
                                        {
                                            "parent_N_membership": "PROVED",
                                            "parent_N_word": nw,
                                        }
                                    )
                            except ValueError:
                                pass
                        targets.append(t)
                cert["supported_image_lifts"] = lifts
                row.update(
                    {
                        "targets": targets,
                        "target_found": len(lifts),
                        "target_required": len(C.N) * a.d,
                        "completion": completion,
                        "maximum_parent_length": max(
                            (len(z["parent_word"]) for z in lifts), default=0
                        ),
                    }
                )
                if len(lifts) == len(C.N) * a.d:
                    replay = verify_supported_image_certificate(
                        packet,
                        cert,
                        {**L, "seconds": max(0.01, a.deadline - time.monotonic())},
                    )
                    row["verification"] = replay
                    if replay["status"] == "PASS_I_BOUND":
                        row["status"] = "CERTIFIED_I_BOUND"
                        ans["certificates"].append(
                            {
                                "candidate_type": C.kind,
                                "certificate": cert,
                                "verification": replay,
                            }
                        )
                        ans["status"] = "CERTIFIED_I_BOUND"
            except Limit as e:
                row["limit_reached"] = str(e)
                row.setdefault("target_found", len(complete))
                row.setdefault("target_required", len(C.N) * a.d)
            except Exception as e:
                row.update({"status": "ERROR", "error": repr(e)})
        ans["local_word_pool"] = pool.export()
        ans["diagnostics"]["shared_pool"].update(pool.stats())
        ans["rankings"] = sorted(
            [
                {
                    "candidate_type": z["candidate_type"],
                    "status": z["status"],
                    "target_found": z.get("target_found", 0),
                    "target_required": z.get("target_required"),
                    "cover_upper_bound": z.get("cover_upper_bound"),
                }
                for z in ans["candidates"]
            ],
            key=lambda z: (
                z["status"] != "CERTIFIED_I_BOUND",
                -(z["target_found"] / max(1, z["target_required"] or 1)),
            ),
        )
    except Limit as e:
        ans["diagnostics"]["limit_reached"] = str(e)
    except Exception as e:
        ans["status"] = "ERROR"
        ans["diagnostics"]["error"] = repr(e)
    ans["elapsed_seconds"] = time.monotonic() - start
    return ans


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("--output")
    p.add_argument("--basis-hint")
    p.add_argument("--seconds", type=float, default=30)
    p.add_argument("--word-count", type=int, default=100000)
    args = p.parse_args()
    r = run_case(
        json.load(open(args.input)),
        {"seconds": args.seconds, "word_count": args.word_count},
        json.load(open(args.basis_hint)) if args.basis_hint else None,
    )
    s = json.dumps(r, indent=2)
    if args.output:
        open(args.output, "w").write(s + "\n")
        print(
            json.dumps(
                {
                    k: v
                    for k, v in r.items()
                    if k not in ("candidates", "certificates", "local_word_pool")
                }
            )
        )
    else:
        print(s)
