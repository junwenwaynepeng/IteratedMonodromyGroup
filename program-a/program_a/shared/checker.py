"""Hardened finite direct-image upper-bound certificate checker. No search/GAP.
A PASS checks every signed right-coset transition on the whole tree.
"""

import time, json, os
from .exact import (
    Action,
    Invalid,
    Limit,
    require,
    integer,
    word,
    expand,
    inv,
    digest,
    CONVENTION,
)

SCHEMA = "direct_image_cover_v1"
CAPS = {
    "basis_rank": 64,
    "tuple_generators": 10000,
    "cosets": 10000,
    "transitions": 2000000,
    "word_length": 100000,
    "expanded_total_letters": 100000000,
}


def verify(packet, c, values=None):
    start = time.monotonic()
    a = None
    where = "admission"
    expanded = 0
    try:
        require(__debug__, "Python optimization is unsupported; run without -O")
        a = Action(packet, values)
        cap = min(CAPS["word_length"], a.L["word_length"])
        require(type(c) is dict and c.get("schema") == SCHEMA, "certificate schema")
        require(c.get("convention") == CONVENTION, "composition convention")
        require(
            c.get("model_sha256") == digest(packet.get("model", packet)),
            "model hash mismatch",
        )
        require(
            c.get("input_packet_sha256") == digest(packet), "input packet hash mismatch"
        )
        require(c.get("map_id") == packet.get("map_id"), "map identity mismatch")
        require(
            c.get("table_sha256") == packet.get("table_sha256"),
            "table identity mismatch",
        )
        B = c.get("basis_words")
        G = c.get("original_generator_words")
        require(type(B) is list and 1 <= len(B) <= CAPS["basis_rank"], "basis size")
        B = [word(w, a.q, cap, "basis word") for w in B]
        r = len(B)
        require(type(G) is list and len(G) == a.q, "reverse generation count")
        G = [word(w, r, cap, "original-generator basis expression") for w in G]
        where = "basis_reverse_generation"
        for i, w in enumerate(G, 1):
            require(
                a.equal(expand(w, B, cap), (i,)),
                "basis does not generate original state " + str(i),
            )
        T = c.get("tuple_generators")
        R = c.get("coset_representatives")
        Z = c.get("transitions")
        require(
            type(T) is list and len(T) <= CAPS["tuple_generators"],
            "tuple generator count",
        )
        require(type(R) is list and 1 <= len(R) <= CAPS["cosets"], "coset count")
        require(
            type(Z) is list
            and len(Z) == len(R) * a.d * 2 * r
            and len(Z) <= CAPS["transitions"],
            "complete transition count",
        )
        tuples = []
        where = "tuple_parents"
        for j, t in enumerate(T):
            require(type(t) is dict, "tuple object")
            p = word(t.get("parent_word"), a.q, cap, "parent word")
            s = t.get("sections")
            require(type(s) is list and len(s) == a.d, "tuple section dimensions")
            s = tuple(word(w, a.q, cap, "section word") for w in s)
            root, actual = a.wreath(p)
            require(root == tuple(range(a.d)), "parent does not fix whole first level")
            require(
                a.tuple_equal(actual, s),
                "advertised tuple is not parent sections " + str(j),
            )
            tuples.append(s)
        reps = []
        where = "representatives"
        for t in R:
            require(type(t) is list and len(t) == a.d, "representative dimensions")
            reps.append(tuple(word(w, a.q, cap, "representative word") for w in t))
        require(
            all(a.identity(w) for w in reps[0]), "first representative is not identity"
        )
        seen = set()
        where = "signed_transitions"
        for z in Z:
            a.tick()
            require(type(z) is dict, "transition object")
            i = integer(z.get("coset"), 0, len(R) - 1, "coset index")
            x = integer(z.get("child"), 0, a.d - 1, "child index")
            g = z.get("letter")
            require(type(g) is int and 0 < abs(g) <= r, "signed basis letter")
            j = integer(z.get("target"), 0, len(R) - 1, "target index")
            key = (i, x, g)
            require(key not in seen, "duplicate transition")
            seen.add(key)
            v = word(z.get("tuple_word"), len(T), cap, "tuple factor expression")
            for y in range(a.d):
                section_images = [t[y] for t in tuples]
                k = expand(v, section_images, cap)
                expanded += len(k)
                if expanded > CAPS["expanded_total_letters"]:
                    raise Limit("expanded_total_letters")
                lhs = (
                    reps[i][y] + (B[g - 1] if g > 0 else inv(B[-g - 1]))
                    if x == y
                    else reps[i][y]
                )
                rhs = k + reps[j][y]
                require(
                    a.equal(lhs, rhs), "false cover transition " + str((i, x, g, y))
                )
        # Count plus unique valid keys forces the full signed transition domain.
        require(len(seen) == len(R) * a.d * 2 * r, "missing signed transitions")
        return {
            "status": "PASS_DIRECT_IMAGE_BOUND",
            "all_level_I_upper_bound": len(R),
            "valid_n_min": 1,
            "cover_size_is_exact_index": False,
            "tuple_generators": len(T),
            "signed_transitions": len(Z),
            "scope": "Pinned supplied action only: K<=psi(St_G(1)), [G^d:psi(St_G(1))]<=cover_size. No geometric/arithmetic or regular-branch upgrade.",
            "elapsed_seconds": time.monotonic() - start,
            "metrics": a.stats,
        }
    except Limit as e:
        return {
            "status": "UNKNOWN",
            "reason": str(e),
            "stage": where,
            "elapsed_seconds": time.monotonic() - start,
            "metrics": a.stats if a else {},
        }
    except (Invalid, KeyError, IndexError, TypeError, ValueError) as e:
        return {
            "status": "FAIL",
            "reason": str(e),
            "stage": where,
            "elapsed_seconds": time.monotonic() - start,
            "metrics": a.stats if a else {},
        }


def package(packet, B, G, T, R, Z):
    return {
        "schema": SCHEMA,
        "convention": CONVENTION,
        "map_id": packet.get("map_id"),
        "table_sha256": packet.get("table_sha256"),
        "model_sha256": digest(packet.get("model", packet)),
        "input_packet_sha256": digest(packet),
        "basis_words": [list(w) for w in B],
        "original_generator_words": [list(w) for w in G],
        "tuple_generators": [
            {
                "parent_word": list(t["parent_word"]),
                "sections": [list(w) for w in t["sections"]],
            }
            for t in T
        ],
        "coset_representatives": [[list(w) for w in t] for t in R],
        "transitions": Z,
    }
