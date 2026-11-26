"""Bounded practical Program A N-discovery, independent of map/name identifiers.
No finite-depth test accepts a certificate. The caller controls wallclock and word caps.
"""

import json, time, argparse, itertools
from collections import deque
from ...shared.weak_verify import (
    Action,
    Limit,
    inv,
    expand,
    verify_certificate,
    verify_subgroup_certificate,
)

DEFAULT = {
    "seconds": 8,
    "identity_states": 4000,
    "basis_cap": 3,
    "basis_pairs": 12000,
    "word_depth": 10,
    "word_count": 12000,
    "coset_cap": 64,
    "fingerprint_depth": 2,
    "basis_word_depth": 6,
    "basis_word_count": 30000,
    "basis_strategy": "sparse",
    "universal_moduli": [2, 3],
    "basis_exchange": True,
    "basis_seed": [],
}


def reduce_invol(w):
    out = []
    for g in w:
        g = abs(g)
        if out and out[-1] == g:
            out.pop()
        else:
            out.append(g)
    return tuple(out)


def words(r, depth, cap, invol=True):
    yield ()
    level = [()]
    count = 1
    for length in range(1, depth + 1):
        nxt = []
        for w in level:
            for g in (
                range(1, r + 1)
                if invol
                else tuple(range(1, r + 1)) + tuple(range(-r, 0))
            ):
                if w and (w[-1] == g if invol else w[-1] == -g):
                    continue
                u = w + (g,)
                yield u
                count += 1
                if count >= cap:
                    return
                nxt.append(u)
        level = nxt


def find_basis(a, L):
    targets = sorted(
        {a.alias[g] for g in range(1, a.q + 1)} - {0},
        key=(
            (lambda x: (sum(t != 0 for t in a.raw[x][1]), abs(x), x < 0))
            if L["basis_strategy"] == "sparse"
            else (lambda x: (abs(x), x < 0))
        ),
    )
    known = {0: ()}
    B = []
    paircount = 0
    ballcount = 0
    seed = {a.alias[g]: i for i, g in enumerate(L["basis_seed"])}
    order = {g: i for i, g in enumerate(targets)}
    targets.sort(key=lambda g: (0, seed[g]) if g in seed else (1, order[g]))
    a.basis_diagnostics = {
        "strategy": L["basis_strategy"],
        "word_depth": L["basis_word_depth"],
        "word_count_cap": L["basis_word_count"],
    }

    def remember(g, w):
        known[g] = w
        known[a.alias[-g]] = inv(w)

    while any(g not in known for g in targets):
        g = next(g for g in targets if g not in known)
        if len(B) >= L["basis_cap"]:
            if L["basis_exchange"]:
                attempts = []
                best = dict(a.basis_diagnostics)
                for index in range(len(B)):
                    seeds = [v[0] for v in B]
                    seeds[index] = g
                    try:
                        answer = find_basis(
                            a, {**L, "basis_exchange": False, "basis_seed": seeds}
                        )
                        a.basis_diagnostics["successful_exchange_seed"] = seeds
                        return answer
                    except Limit as exc:
                        attempts.append(
                            {
                                "seed": seeds,
                                "limit": str(exc),
                                "known_original_states": a.basis_diagnostics.get(
                                    "known_original_states"
                                ),
                            }
                        )
                        if a.basis_diagnostics.get(
                            "known_original_states", 0
                        ) > best.get("known_original_states", 0):
                            best = dict(a.basis_diagnostics)
                        if str(exc) == "wallclock_seconds":
                            raise
                a.basis_diagnostics = best
                a.basis_diagnostics["exchange_attempts"] = attempts
            raise Limit("basis_cap")
        B.append((g,))
        remember(g, (len(B),))
        changed = True
        while changed:
            changed = False
            pool = [(g, w) for g, w in known.items() if g]
            unknown = [g for g in targets if g not in known]
            if not unknown:
                break
            fingerprints = {
                g: a.fingerprint((g,), L["fingerprint_depth"]) for g in unknown
            }
            for g, w in pool:
                for h, v in pool:
                    a.tick()
                    paircount += 1
                    if paircount > L["basis_pairs"]:
                        raise Limit("basis_pairs")
                    f = a.fingerprint((g, h), L["fingerprint_depth"])
                    for target in list(unknown):
                        if fingerprints[target] == f and a.equal((g, h), (target,)):
                            remember(target, w + v)
                            unknown.remove(target)
                            changed = True
                    if not unknown:
                        break
                if not unknown:
                    break
        # Unlike products of known ORIGINAL states, this ball explores arbitrary
        # signed basis words. Finite permutations filter; each match is exact.
        unknown = [g for g in targets if g not in known]
        if unknown and len(B) >= min(2, L["basis_cap"]):
            depth = L["fingerprint_depth"]
            fingerprints = {}
            for target in unknown:
                fingerprints.setdefault(a.fingerprint((target,), depth), []).append(
                    target
                )
            perms = {
                g: a.fingerprint(expand((g,), B), depth)
                for g in tuple(range(1, len(B) + 1)) + tuple(range(-len(B), 0))
            }
            identity = tuple(range(a.d**depth))
            level = [((), identity)]
            foundall = False
            localcount = 0
            for length in range(1, L["basis_word_depth"] + 1):
                nxt = []
                for w, p in level:
                    for letter, pg in perms.items():
                        if w and w[-1] == -letter:
                            continue
                        a.tick()
                        localcount += 1
                        ballcount += 1
                        if localcount > L["basis_word_count"]:
                            break
                        v = w + (letter,)
                        f = tuple(pg[p[x]] for x in range(len(p)))
                        for target in list(fingerprints.get(f, ())):
                            if target not in known and a.equal(expand(v, B), (target,)):
                                remember(target, v)
                        if all(g in known for g in targets):
                            foundall = True
                            break
                        nxt.append((v, f))
                    if foundall or localcount > L["basis_word_count"]:
                        break
                if foundall or localcount > L["basis_word_count"]:
                    break
                level = nxt
            a.basis_diagnostics.update(
                {
                    "ball_words_tested": ballcount,
                    "known_original_states": sum(g in known for g in targets),
                    "required_original_states": len(targets),
                    "current_basis_words": B,
                }
            )
    a.basis_diagnostics.update(
        {
            "known_original_states": len(targets),
            "required_original_states": len(targets),
            "current_basis_words": B,
        }
    )
    return B, [known[a.alias[g]] for g in range(1, a.q + 1)], paircount


class Cover:
    def __init__(self, a, B, kind, cap):
        self.a = a
        self.B = B
        self.r = len(B)
        self.kind = kind
        self.reps = [()]
        self.states = [
            (
                (0,) * len(B)
                if (
                    kind.startswith("universal_mod_")
                    or kind.startswith("universal_mixed_")
                )
                else (
                    0
                    if kind in ("involution_derived", "root_sign_kernel")
                    else tuple(range(a.d))
                )
            )
        ]
        self.edges = {}
        self.N = []
        self.Nbasis = []
        self.transitions = {}
        rootgens = [a.root(w) for w in B]

        def transition(s, g):
            if kind.startswith("universal_mixed_"):
                moduli = tuple(map(int, kind[len("universal_mixed_") :].split("_")))
                v = list(s)
                v[abs(g) - 1] = (v[abs(g) - 1] + (1 if g > 0 else -1)) % moduli[
                    abs(g) - 1
                ]
                return tuple(v)
            if kind.startswith("universal_mod_"):
                modulus = int(kind.rsplit("_", 1)[1])
                v = list(s)
                v[abs(g) - 1] = (v[abs(g) - 1] + (1 if g > 0 else -1)) % modulus
                return tuple(v)
            if kind == "involution_derived":
                return s ^ (1 << (abs(g) - 1))
            if kind == "root_sign_kernel":
                p = rootgens[abs(g) - 1]
                return s ^ (
                    sum(p[i] > p[j] for i in range(a.d) for j in range(i + 1, a.d)) % 2
                )
            p = rootgens[abs(g) - 1]
            if g < 0:
                p = tuple(p.index(x) for x in range(a.d))
            return tuple(p[s[x]] for x in range(a.d))

        self.transition = transition
        queue = deque([0])
        letters = list(range(1, self.r + 1)) + list(range(-self.r, 0))
        while queue:
            i = queue.popleft()
            for g in letters:
                s = transition(self.states[i], g)
                if s not in self.states:
                    if len(self.states) >= cap:
                        raise Limit("coset_cap")
                    self.states.append(s)
                    self.reps.append(self.reps[i] + (g,))
                    queue.append(len(self.states) - 1)
                j = self.states.index(s)
                self.transitions[i, g] = j
        for i in range(len(self.reps)):
            for g in letters:
                j = self.transitions[i, g]
                v = self.reps[i] + (g,) + inv(self.reps[j])
                raw = expand(v, B)
                if a.identity(raw):
                    self.edges[i, g] = 0
                    continue
                found = None
                for k, n in enumerate(self.N, 1):
                    if a.equal(raw, n):
                        found = k
                        break
                    if a.equal(raw, inv(n)):
                        found = -k
                        break
                if found is None:
                    self.N.append(raw)
                    self.Nbasis.append(v)
                    found = len(self.N)
                self.edges[i, g] = found

    def rewrite(self, w):
        i = 0
        out = []
        for g in w:
            k = self.edges[i, g]
            if k:
                out.append(k)
            i = self.transitions[i, g]
        if i:
            raise ValueError("Formal cover endpoint not identity")
        return out

    def certificate(self, original):
        letters = list(range(1, self.r + 1)) + list(range(-self.r, 0))
        return {
            "schema_version": 1,
            "basis_words": self.B,
            "original_generator_words": original,
            "N_generators": self.N,
            "coset_cover": {
                "representatives": [expand(t, self.B) for t in self.reps],
                "transitions": [
                    {
                        "coset": i,
                        "letter": g,
                        "target": self.transitions[i, g],
                        "N_word": [self.edges[i, g]] if self.edges[i, g] else [],
                    }
                    for i in range(len(self.reps))
                    for g in letters
                ],
            },
            "normality": [
                {
                    "N_generator": i,
                    "letter": g,
                    "N_word": self.rewrite((-g,) + n + (g,)),
                }
                for i, n in enumerate(self.Nbasis, 1)
                for g in letters
            ],
            "supported_lifts": [],
        }


def collect_invol(w):
    cur = reduce_invol(w)
    factors = []
    while any(cur[i] > cur[i + 1] for i in range(len(cur) - 1)):
        i = next(i for i in range(len(cur) - 1) if cur[i] > cur[i + 1])
        prefix = cur[:i]
        x, y = cur[i : i + 2]
        factors.append((prefix, (y, x), -1))
        cur = reduce_invol(cur[:i] + (y, x) + cur[i + 2 :])
    if cur:
        raise ValueError("Not in formal derived subgroup")
    return factors


def discover_lifts_v1(a, B, original, C, L, progress=None):
    r = len(B)
    comm = {(i, j): (i, j, i, j) for i in range(1, r + 1) for j in range(i + 1, r + 1)}
    primitive = {}
    projection = {}
    roottrans = {0: ()}
    direct = {}
    weak = {}
    count = 0
    progress = {} if progress is None else progress
    isolated = []
    invol = all(a.identity(b + b) for b in B)
    for w in words(r, L["word_depth"], L["word_count"], invol):
        a.tick()
        count += 1
        raw = expand(w, B)
        root = a.root(raw)
        if count % 100 == 1:
            progress.update(
                {
                    "searched_words": count,
                    "primitive_commutators_found": len(primitive),
                    "primitive_commutators_required": len(comm),
                    "projection_generators_found": len(projection),
                    "projection_generators_required": r,
                    "root_transports_found": len(roottrans),
                    "direct_supported_pairs": len(direct),
                    "isolated_target_candidates": isolated,
                    "missing_supported_pairs": [
                        [i, x]
                        for i in range(1, len(C.N) + 1)
                        for x in range(a.d)
                        if (i, x) not in direct
                    ],
                }
            )
        for x in range(a.d):
            if root[0] == x and x not in roottrans:
                roottrans[x] = w
        if root != tuple(range(a.d)):
            continue
        sections = [a.step(raw, x)[1] for x in range(a.d)]
        for g in range(1, r + 1):
            if g not in projection and a.equal(sections[0], B[g - 1]):
                projection[g] = w
        if C.kind == "involution_derived" and all(
            sum(g == j for g in w) % 2 == 0 for j in range(1, r + 1)
        ):
            if all(a.identity(s) for s in sections[1:]):
                for pair, c in comm.items():
                    if pair not in primitive and a.equal(sections[0], expand(c, B)):
                        primitive[pair] = w
        # Weak supported-image witnesses do not require the parent to be in N.
        # They are logged separately and NEVER satisfy the strong verifier.
        nontriv = [x for x, s in enumerate(sections) if not a.identity(s)]
        if len(nontriv) == 1:
            x = nontriv[0]
            for i, n in enumerate(C.N, 1):
                if (i, x) not in weak and a.equal(sections[x], n):
                    weak[i, x] = {
                        "N_generator": i,
                        "child": x,
                        "parent_word": raw,
                        "scope": "weak supported image only; parent N membership NOT asserted",
                    }
        progress["weak_supported_lifts"] = list(weak.values())
        try:
            C.rewrite(w)
        except ValueError:
            continue
        if len(nontriv) == 1:
            x = nontriv[0]
            if len(isolated) < 12 and not any(
                a.equal(sections[x], z["target_word"]) for z in isolated
            ):
                isolated.append(
                    {
                        "child": x,
                        "target_word": sections[x],
                        "isolated_parent_word": raw,
                        "finite_index_status": "UNKNOWN",
                        "normality_status": "NORMAL_CLOSURE_CANDIDATE_ONLY",
                        "parent_N_membership": "UNKNOWN",
                    }
                )
            for i, n in enumerate(C.N, 1):
                if (i, x) not in direct and a.equal(sections[x], n):
                    direct[i, x] = w
        if len(direct) == len(C.N) * a.d:
            break
        if (
            C.kind == "involution_derived"
            and len(primitive) == len(comm)
            and len(projection) == r
            and len(roottrans) == a.d
        ):
            break
    diagnostics = {
        "searched_words": count,
        "primitive_commutators_found": len(primitive),
        "primitive_commutators_required": len(comm),
        "projection_generators_found": len(projection),
        "projection_generators_required": r,
        "root_transports_found": len(roottrans),
        "direct_supported_pairs": len(direct),
    }
    if (
        C.kind == "involution_derived"
        and len(primitive) == len(comm)
        and len(projection) == r
        and len(roottrans) == a.d
    ):

        def proj(w):
            return reduce_invol(
                g
                for x in w
                for g in (projection[abs(x)] if x > 0 else inv(projection[abs(x)]))
            )

        for i, n in enumerate(C.Nbasis, 1):
            parent = ()
            for prefix, pair, sign in collect_invol(n):
                t = proj(prefix)
                v = primitive[pair]
                v = v if sign > 0 else inv(v)
                parent = reduce_invol(parent + t + v + inv(t))
            for x, t in roottrans.items():
                u = a.step(expand(t, B), 0)[1]
                ub = tuple(
                    g
                    for s in u
                    for g in (
                        original[abs(s) - 1] if s > 0 else inv(original[abs(s) - 1])
                    )
                )
                liftu = proj(ub)
                px = reduce_invol(inv(t) + liftu + parent + inv(liftu) + t)
                direct[i, x] = px
    lifts = []
    missing = []
    for i in range(1, len(C.N) + 1):
        for x in range(a.d):
            if (i, x) not in direct:
                missing.append([i, x])
                continue
            lifts.append(
                {"N_generator": i, "child": x, "parent_N_word": C.rewrite(direct[i, x])}
            )
    diagnostics["missing_supported_pairs"] = missing
    diagnostics["weak_supported_lifts"] = list(weak.values())
    diagnostics["isolated_target_candidates"] = isolated
    progress.update(diagnostics)
    return lifts, diagnostics


def collect_mod2(w):
    """Exact free-word collection into conjugates of squares/commutators."""
    cur = tuple(w)
    factors = []
    while any(g < 0 for g in cur):
        i = next(i for i, g in enumerate(cur) if g < 0)
        g = -cur[i]
        p = cur[:i]
        factors.append((p, ("square", g), -1))
        cur = cur[:i] + (g,) + cur[i + 1 :]
    while cur:
        doubles = next((i for i in range(len(cur) - 1) if cur[i] == cur[i + 1]), None)
        if doubles is not None:
            i = doubles
            factors.append((cur[:i], ("square", cur[i]), 1))
            cur = cur[:i] + cur[i + 2 :]
            continue
        inversion = next((i for i in range(len(cur) - 1) if cur[i] > cur[i + 1]), None)
        if inversion is None:
            raise ValueError("Nonzero exponent parity")
        i = inversion
        x, y = cur[i : i + 2]
        factors.append((cur[:i], ("comm", y, x), -1))
        cur = cur[:i] + (y, x) + cur[i + 2 :]
    return factors


def discover_mod2_lifts(a, B, original, C, L, progress):
    r = len(B)
    targets = {("square", g): (g, g) for g in range(1, r + 1)}
    targets.update(
        {
            ("comm", i, j): (i, j, -i, -j)
            for i in range(1, r + 1)
            for j in range(i + 1, r + 1)
        }
    )
    primitive = {key: ((), 0) for key, w in targets.items() if a.identity(expand(w, B))}
    projection = {}
    trans = {0: ()}
    count = 0

    def progress_now():
        progress.update(
            {
                "searched_words": count,
                "primitive_targets_found": len(primitive),
                "primitive_targets_required": len(targets),
                "projection_generators_found": len(projection),
                "root_transports_found": len(trans),
                "missing_primitive_targets": [
                    list(k) for k in targets if k not in primitive
                ],
            }
        )

    for w in words(
        r, L["word_depth"], L["word_count"], all(a.identity(b + b) for b in B)
    ):
        a.tick()
        count += 1
        raw = expand(w, B)
        root = a.root(raw)
        if root[0] not in trans:
            trans[root[0]] = w
        if count % 100 == 1:
            progress_now()
        if root != tuple(range(a.d)):
            continue
        sec = [a.step(raw, x)[1] for x in range(a.d)]
        for g in range(1, r + 1):
            if g not in projection and a.equal(sec[0], B[g - 1]):
                projection[g] = w
        try:
            C.rewrite(w)
        except ValueError:
            continue
        nontriv = [x for x, v in enumerate(sec) if not a.identity(v)]
        if len(nontriv) == 1:
            x = nontriv[0]
            for key, target in targets.items():
                if key not in primitive and a.equal(sec[x], expand(target, B)):
                    primitive[key] = (w, x)
        if (
            len(primitive) == len(targets)
            and len(projection) == r
            and len(trans) == a.d
        ):
            break
    progress_now()
    progress["missing_supported_pairs"] = [
        [i, x] for i in range(1, len(C.N) + 1) for x in range(a.d)
    ]
    if len(primitive) != len(targets) or len(projection) != r or len(trans) != a.d:
        return [], progress

    def proj(w):
        return tuple(
            y
            for x in w
            for y in (projection[abs(x)] if x > 0 else inv(projection[abs(x)]))
        )

    def as_basis(raw):
        return tuple(
            y
            for x in raw
            for y in (original[abs(x) - 1] if x > 0 else inv(original[abs(x) - 1]))
        )

    normalized = {}
    for key, (p, x) in primitive.items():
        t = trans[x]
        u = as_basis(a.step(expand(t, B), 0)[1])
        lu = proj(u)
        normalized[key] = inv(lu) + t + p + inv(t) + lu
    lifts = []
    for i, n in enumerate(C.Nbasis, 1):
        p = ()
        for prefix, key, sign in collect_mod2(n):
            t = proj(prefix)
            v = normalized[key]
            v = v if sign > 0 else inv(v)
            p += t + v + inv(t)
        for x, t in trans.items():
            u = as_basis(a.step(expand(t, B), 0)[1])
            lu = proj(u)
            px = inv(t) + lu + p + inv(lu) + t
            lifts.append({"N_generator": i, "child": x, "parent_N_word": C.rewrite(px)})
    progress["missing_supported_pairs"] = []
    return lifts, progress


def discover_lifts(a, B, original, C, L, progress=None):
    if C.kind == "universal_mod_2":
        return discover_mod2_lifts(
            a, B, original, C, L, {} if progress is None else progress
        )
    return discover_lifts_v1(a, B, original, C, L, progress)


def run_case(packet, limits=None):
    L = dict(DEFAULT)
    L.update(limits or {})
    start = time.monotonic()
    result = {
        "schema_version": 1,
        "status": "NO_CERT_WITHIN_LIMIT",
        "map_id": packet.get("map_id"),
        "limits": L,
        "candidates": [],
        "diagnostics": {},
        "scope": "supplied finite-state action; finite fingerprints only filter; no map realization claimed",
    }
    try:
        a = Action(packet, L)
        B, original, pairs = find_basis(a, L)
        result["diagnostics"].update(
            {
                "basis_words": B,
                "basis_size": len(B),
                "basis_pair_tests": pairs,
                "original_generator_words": original,
            }
        )
        invol = all(a.identity(b + b) for b in B)
        kinds = (
            (["involution_derived"] if invol and 2 ** len(B) <= L["coset_cap"] else [])
            + ["root_sign_kernel", "root_kernel"]
            + [
                "universal_mod_" + str(m)
                for m in L["universal_moduli"]
                if m ** len(B) <= L["coset_cap"] and not (invol and m == 2)
            ]
        )
        global_deadline = start + L["seconds"]
        for family_index, kind in enumerate(kinds):
            if time.monotonic() >= global_deadline:
                break
            budget = max(
                0.001,
                (global_deadline - time.monotonic()) / (len(kinds) - family_index),
            )
            a.deadline = min(global_deadline, time.monotonic() + budget)
            row = {
                "candidate_type": kind,
                "finite_index_status": "NOT_YET_VERIFIED",
                "family_budget_seconds": budget,
            }
            result["candidates"].append(row)
            try:
                a.tick()
                C = Cover(a, B, kind, L["coset_cap"])
                row.update(
                    {
                        "N_generators": C.N,
                        "N_generator_count": len(C.N),
                        "index_cover_size": len(C.reps),
                        "finite_index_status": "WORD_COVER_CONSTRUCTED",
                        "exact_quotient_status": (
                            "NOT_ESTABLISHED"
                            if kind == "involution_derived"
                            or (
                                kind.startswith("universal_mod_")
                                or kind.startswith("universal_mixed_")
                            )
                            else (
                                "ROOT_SIGN_CANDIDATE"
                                if kind == "root_sign_kernel"
                                else "ROOT_ACTION_CANDIDATE"
                            )
                        ),
                    }
                )
                cert = C.certificate(original)
                partial = verify_subgroup_certificate(
                    packet,
                    cert,
                    {**L, "seconds": max(0.001, a.deadline - time.monotonic())},
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
                row["diagnostics"] = {}
                lifts, diagnostics = discover_lifts(
                    a, B, original, C, L, row["diagnostics"]
                )
                cert["supported_lifts"] = lifts
                if diagnostics["missing_supported_pairs"]:
                    row["status"] = "NO_CERT_WITHIN_LIMIT"
                    continue
                remaining = max(0.001, a.deadline - time.monotonic())
                replay = verify_certificate(packet, cert, {**L, "seconds": remaining})
                row["verification"] = replay
                row["status"] = (
                    "CERTIFIED"
                    if replay["status"] == "PASS"
                    else "NO_CERT_WITHIN_LIMIT"
                )
                if replay["status"] == "PASS":
                    result.update(
                        {
                            "status": "CERTIFIED_N",
                            "certificate": cert,
                            "verification": replay,
                            "candidate_type": kind,
                        }
                    )
                    break
            except Limit as e:
                row.update({"status": "NO_CERT_WITHIN_LIMIT", "limit_reached": str(e)})
                continue
            except Exception as e:
                row.update({"status": "ERROR", "error": repr(e)})
                continue
    except Limit as e:
        result["diagnostics"]["limit_reached"] = str(e)
    except Exception as e:
        result["status"] = "ERROR"
        result["diagnostics"]["error"] = repr(e)
    if "a" in locals() and hasattr(a, "basis_diagnostics"):
        result["diagnostics"]["basis_ball"] = a.basis_diagnostics
    result["elapsed_seconds"] = time.monotonic() - start
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("--output")
    p.add_argument("--seconds", type=float, default=8)
    p.add_argument("--word-depth", type=int, default=10)
    p.add_argument("--word-count", type=int, default=12000)
    args = p.parse_args()
    r = run_case(
        json.load(open(args.input)),
        {
            "seconds": args.seconds,
            "word_depth": args.word_depth,
            "word_count": args.word_count,
        },
    )
    s = json.dumps(r, indent=2)
    print(
        s
        if not args.output
        else json.dumps(
            {k: v for k, v in r.items() if k not in ["certificate", "candidates"]}
        )
    )
    if args.output:
        open(args.output, "w").write(s + "\n")
