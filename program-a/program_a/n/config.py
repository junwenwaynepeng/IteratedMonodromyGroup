"""Explicit bounded N-method configuration; no admission, native process or run at import."""

import copy, math
from ..contracts import need, digest
from .legacy.pool import DEFAULT as HISTORICAL

DEFAULT = {
    **HISTORICAL,
    "seconds": 30.0,
    "basis_cap": 8,
    "word_count": 20000,
    "word_depth": 12,
    "candidate_build_seconds": 5.0,
    "candidate_limit": 16,
    "completion_every_words": 256,
    "completion_round_seconds": 3.0,
    "partial_cap": 256,
    "partial_pair_tests": 10000,
    "partial_bucket_cap": 8,
    "search_cache_cap": 20000,
    "tuple_cap": 10000,
    "N_word_count": 2000,
    "N_word_depth": 6,
    "N_word_batch": 32,
    "membership_nodes": 10000,
    "membership_depth": 4,
    "normal_conjugator_depth": 1,
    "normal_conjugator_count": 100,
    "raw_seconds": 10.0,
    "raw_identity_states": 100000,
    "verify_seconds": 10.0,
    "output_bytes": 8 * 1024**2,
    "export_word_length": 100000,
    "families": ["root_sign_kernel", "root_kernel", "universal_mod_2"],
    "normal_closure_families": [],
    "normal_closure_seeds": [],
    "index_backend": "normal_cover",
    "strength": "both",
}


def normalize(overrides=None):
    z = copy.deepcopy(DEFAULT)
    for k, v in (overrides or {}).items():
        need(k in z, "UNKNOWN_N_LIMIT:" + k)
        z[k] = copy.deepcopy(v)
    for k, v in z.items():
        if isinstance(DEFAULT[k], (int, float)) and not isinstance(DEFAULT[k], bool):
            need(
                type(v) in (int, float) and math.isfinite(v) and v > 0,
                "POSITIVE_N_LIMIT:" + k,
            )
            if isinstance(DEFAULT[k], int):
                need(type(v) is int, "INTEGER_N_LIMIT:" + k)
    need(z["strength"] in ["weak", "strong", "both"], "N_STRENGTH")
    need(
        z["index_backend"] in ["normal_cover", "native_index", "gap_felsch"],
        "N_INDEX_BACKEND",
    )
    need(
        type(z["families"]) is list and len(z["families"]) <= z["candidate_limit"],
        "N_FAMILY_LIST",
    )
    need(type(z["normal_closure_seeds"]) is list, "NORMAL_CLOSURE_SEEDS")
    need(
        type(z["normal_closure_families"]) is list
        and set(z["normal_closure_families"])
        <= set(["commutators", "pair_differences"]),
        "NORMAL_CLOSURE_FAMILY",
    )
    return z


def structural(z):
    # A continuation may add budget/capacity. Its candidate/strategy/alphabet semantics cannot change.
    return digest(
        {
            k: z[k]
            for k in [
                "families",
                "universal_moduli",
                "normal_closure_families",
                "normal_closure_seeds",
                "normal_conjugator_depth",
                "normal_conjugator_count",
                "index_backend",
                "strength",
            ]
        }
    )
