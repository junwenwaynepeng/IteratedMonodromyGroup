"""A weaker Program A certificate: exact supported image, parents need not lie in N.
This proves an all-level I bound, not regular branching over N or a J,U recurrence.
"""

import importlib.util, json, pathlib, sys
from .weak_verify import Action, Limit, verify_subgroup_certificate


def verify_supported_image_certificate(model, cert, limits=None):
    result = verify_subgroup_certificate(model, cert, limits)
    if result["status"] != "PASS_SUBGROUP_DATA":
        return result
    try:
        if not __debug__:
            raise ValueError("Assertions must remain enabled")
        a = Action(model, limits)
        N = cert["N_generators"]
        rows = {}
        for r in cert["supported_image_lifts"]:
            key = r["N_generator"], r["child"]
            assert key not in rows
            rows[key] = r
        assert set(rows) == {(i, x) for i in range(1, len(N) + 1) for x in range(a.d)}
        for (i, x), r in rows.items():
            p = r["parent_word"]
            for y in range(a.d):
                target = N[i - 1] if y == x else []
                out, sec = a.step(p, y)
                assert out == y and a.equal(sec, target), ("supported_image", i, x, y)
        k = result["index_upper_bound"]
        return {
            "status": "PASS_I_BOUND",
            "index_upper_bound": k,
            "all_level_I_upper_bound": k**a.d,
            "valid_n_min": 1,
            "scope": "N^d<=psi(St1) only; parents are actual group words, not asserted inN",
            "regular_branch_over_N": "NOT_ESTABLISHED",
            "exact_quotient_or_U_recurrence": "NOT_ESTABLISHED",
            "whole_tree_checks": a.checks,
        }
    except Limit as e:
        return {"status": "UNKNOWN", "reason": str(e)}
    except Exception as e:
        return {"status": "FAIL", "reason": repr(e)}
