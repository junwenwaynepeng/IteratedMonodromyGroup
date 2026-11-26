"""Small witnessed covers. Unknown membership never proves distinct cosets.

Only exact membership expressions create transitions or merge representatives.
The unchanged whole-tree checker decides whether a final package is valid.
"""

import time
from collections import Counter
from .exact import free, inv, require
from .tuples import multiply, inverse


def compact_certificate(c):
    """Drop unused tuple generators and renumber their explicit witness words."""
    used = sorted({abs(g) for z in c["transitions"] for g in z["tuple_word"]})
    require(
        all(1 <= i <= len(c["tuple_generators"]) for i in used), "Tuple witness range"
    )
    mapping = {i: j + 1 for j, i in enumerate(used)}
    out = dict(c, tuple_generators=[c["tuple_generators"][i - 1] for i in used])
    out["transitions"] = [
        dict(
            z,
            tuple_word=[
                (1 if g > 0 else -1) * mapping[abs(g)] for g in z["tuple_word"]
            ],
        )
        for z in c["transitions"]
    ]
    return out


from .cover_search.engine import CoverSearch


class SmallCosetSearch(CoverSearch):
    """Existing entry/signature; strategies live entirely in cover_search."""

    pass
