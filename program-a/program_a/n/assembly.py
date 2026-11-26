"""Original checkers and a separate raw interpreter. No candidate or witness search."""

import copy, time
from ..contracts import need, digest
from ..shared.weak_verify import verify_certificate, verify_subgroup_certificate
from ..shared.weak_image import verify_supported_image_certificate
from ..shared.exact import Action as RawAction, word, expand, inv, Limit as RawLimit


def raw_check(packet, cert, strength, limits):
    """Independently expand every obligation with formal cancellation only; no alias interpreter."""
    start = time.monotonic()
    try:
        a = RawAction(
            packet,
            {
                "seconds": limits["seconds"],
                "identity_states": limits["identity_states"],
                "word_length": limits.get("word_length", 100000),
            },
        )
        B = cert["basis_words"]
        N = cert["N_generators"]
        T = cert["coset_cover"]["representatives"]

        def exp(w, images):
            return expand(
                word(w, len(images), a.L["word_length"]), images, a.L["word_length"]
            )

        def eq(u, v):
            need(a.equal(u, v), "RAW_FALSE_IDENTITY")

        need(
            cert["schema_version"] == 1
            and B
            and T
            and len(cert["original_generator_words"]) == a.q,
            "RAW_SCHEMA",
        )
        for w in B + N + T:
            word(w, a.q, a.L["word_length"])
        for i, w in enumerate(cert["original_generator_words"], 1):
            eq(exp(w, B), (i,))
        need(a.identity(T[0]), "RAW_FIRST_COSET_IDENTITY")

        def rows(values, keys, expected):
            z = {}
            for r in values:
                key = tuple(r[k] for k in keys)
                need(key not in z, "RAW_DUPLICATE_OBLIGATION")
                z[key] = r
            need(set(z) == set(expected), "RAW_OBLIGATION_COVERAGE")
            return z

        letters = tuple(range(1, len(B) + 1)) + tuple(range(-len(B), 0))
        edges = rows(
            cert["coset_cover"]["transitions"],
            ["coset", "letter"],
            ((i, g) for i in range(len(T)) for g in letters),
        )
        for (i, g), r in edges.items():
            j = r["target"]
            need(type(j) is int and 0 <= j < len(T), "RAW_COSET_TARGET")
            eq(tuple(T[i]) + exp((g,), B), exp(r["N_word"], N) + tuple(T[j]))
        norms = rows(
            cert["normality"],
            ["N_generator", "letter"],
            ((i, g) for i in range(1, len(N) + 1) for g in letters),
        )
        for (i, g), r in norms.items():
            b = exp((g,), B)
            eq(inv(b) + tuple(N[i - 1]) + b, exp(r["N_word"], N))
        key = "supported_lifts" if strength == "strong" else "supported_image_lifts"
        lifts = rows(
            cert[key],
            ["N_generator", "child"],
            ((i, x) for i in range(1, len(N) + 1) for x in range(a.d)),
        )
        for (i, x), r in lifts.items():
            p = (
                exp(r["parent_N_word"], N)
                if strength == "strong"
                else word(r["parent_word"], a.q, a.L["word_length"])
            )
            for y in range(a.d):
                out, sec = a.step(p, y)
                need(out == y, "RAW_PARENT_ROOT")
                eq(sec, N[i - 1] if y == x else ())
        return {
            "status": "PASS_RAW_N_INSERTION",
            "strength": strength,
            "certificate_sha256": digest(cert),
            "packet_sha256": digest(packet),
            "I_upper_bound": len(T) ** a.d,
            "stats": a.stats,
            "elapsed_seconds": time.monotonic() - start,
            "interpreter": "Independent legacy.exact.Action; formal cancellation only, no weak_verify.Action aliases.",
        }
    except RawLimit as e:
        return {
            "status": "UNKNOWN",
            "reason": str(e),
            "elapsed_seconds": time.monotonic() - start,
        }
    except Exception as e:
        return {
            "status": "FAIL",
            "reason": repr(e),
            "elapsed_seconds": time.monotonic() - start,
        }


def assemble(candidate, G, pool, found, strength, L, *, strong_proofs=None):
    cert = copy.deepcopy(candidate.certificate)
    lifts = []
    for i, n in enumerate(candidate.cover.N, 1):
        for x in range(pool.a.d):
            p = (
                (strong_proofs or {}).get((i, x), {}).get("parent_word")
                if strength == "strong"
                else found.get((i, x))
            )
            if p is None:
                return None
            need(len(p) <= L["export_word_length"], "N_PARENT_EXPORT_CAP")
            if strength == "weak":
                lifts.append({"N_generator": i, "child": x, "parent_word": list(p)})
            else:
                proof = (strong_proofs or {}).get((i, x))
                if proof is None:
                    return None
                nw = proof["parent_N_word"]
                expanded = expand(nw, candidate.cover.N, L["export_word_length"])
                need(pool.a.equal(p, expanded), "STRONG_N_MEMBERSHIP_FALSE")
                lifts.append({"N_generator": i, "child": x, "parent_N_word": list(nw)})
    cert["supported_lifts" if strength == "strong" else "supported_image_lifts"] = lifts
    return cert


def check_and_raw(action, cert, strength, L, clock, remaining):
    seconds = min(L["verify_seconds"], remaining())
    need(seconds > 0, "CHECK_BUDGET_EXHAUSTED")
    with clock.phase("whole_tree_checker"):
        f = (
            verify_certificate
            if strength == "strong"
            else verify_supported_image_certificate
        )
        v = f(
            action.packet,
            cert,
            {"seconds": seconds, "identity_states": L["identity_states"]},
        )
    need(v["status"] != "FAIL", "GENERATED_N_CERTIFICATE_FAIL:" + str(v))
    record = {
        "strength": strength,
        "certificate": cert,
        "certificate_sha256": digest(cert),
        "whole_tree": v,
        "raw": None,
        "identity": action.identity.record(),
        "scope": (
            "N^d<=psi(N intersect St(1))"
            if strength == "strong"
            else "N^d<=H=psi(St(1)); parents need not belong to N"
        ),
    }
    if v["status"] not in ["PASS", "PASS_I_BOUND"]:
        record["status"] = "UNKNOWN_CHECKER"
        return record
    seconds = min(L["raw_seconds"], remaining())
    if seconds <= 0:
        record["status"] = "WHOLE_TREE_PASS_RAW_NOT_RUN_BUDGET"
        return record
    with clock.phase("separate_raw_replay"):
        raw = raw_check(
            action.packet,
            cert,
            strength,
            {
                "seconds": seconds,
                "identity_states": L["raw_identity_states"],
                "word_length": L["export_word_length"],
            },
        )
    need(raw["status"] != "FAIL", "GENERATED_N_RAW_FAIL:" + str(raw))
    record.update(
        raw=raw,
        status=(
            "CERTIFIED_N_BOUND"
            if raw["status"] == "PASS_RAW_N_INSERTION"
            else "WHOLE_TREE_PASS_RAW_UNKNOWN"
        ),
    )
    if record["status"] == "CERTIFIED_N_BOUND":
        record["I_upper_bound"] = v["all_level_I_upper_bound"]
    return record
