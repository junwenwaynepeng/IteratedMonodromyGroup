"""Find or explicitly reuse an exactly generating basis; no expected result lookup."""

from ..contracts import need
from ..shared.weak_verify import expand
from .legacy.cover_tools import find_basis


def obtain(action, L, hint=None):
    if hint is None:
        B, G, _ = find_basis(action, L)
        return (
            B,
            G,
            {
                "mode": "FROM_INPUT_BASIS_DISCOVERY",
                "basis_diagnostics": getattr(action, "basis_diagnostics", {}),
            },
        )
    need(
        type(hint) is dict
        and set(hint) >= {"basis_words", "original_generator_words", "identity"},
        "BOUND_BASIS_HINT",
    )
    B = hint["basis_words"]
    G = hint["original_generator_words"]
    need(bool(B) and len(G) == action.q, "GENERATING_BASIS_DIMENSIONS")
    for i, w in enumerate(G, 1):
        need(action.equal(expand(w, B), (i,)), "BASIS_REVERSE_GENERATION")
    return (
        [tuple(w) for w in B],
        [tuple(w) for w in G],
        {"mode": "SUPPLIED_BASIS_EXACTLY_REPLAYED_NOT_FROM_ZERO"},
    )
