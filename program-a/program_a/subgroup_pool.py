"""Common input boundary for KH and Index. Tuple order is part of the alphabet."""

from collections import deque

from .shared.exact import Action, digest, free, inv, require, validate_model, word


def checked_rows(packet, rows):
    """Check original signed words and dimensions; backends verify the tree action."""
    _, rank, degree = validate_model(packet)
    require(isinstance(rows, (tuple, list)), "expected a tuple list")
    for row in rows:
        word(row["parent_word"], rank)
        require(len(row["sections"]) == degree, "bad tuple degree")
        for section in row["sections"]:
            word(section, rank)
    return rows


def bound_rows(packet, pool):
    """Accept historical pools; check the action binding on newly prepared pools."""
    if "action_sha256" in pool:
        require(pool["action_sha256"] == digest(packet), "tuple pool action mismatch")
    return pool["tuple_generators"]


def pool_rows(packet, pool):
    return checked_rows(packet, bound_rows(packet, pool))


class ConstructionLimit(Exception):
    """Only an incomplete Schreier construction permits the retained-pool fallback."""


def schreier_rows(action, max_quotient=4096, max_rows=65536, max_letters=2000000):
    """Enumerate the root quotient, then take sections of all positive Schreier edges."""
    identity = tuple(range(action.d))
    transversal = {identity: ()}
    queue = deque([identity])
    while queue:
        permutation = queue.popleft()
        for g, generator in enumerate(action.roots, 1):
            target = tuple(generator[x] for x in permutation)
            if target not in transversal:
                if len(transversal) >= max_quotient:
                    raise ConstructionLimit("root quotient")
                transversal[target] = transversal[permutation] + (g,)
                queue.append(target)
    if len(transversal) * action.q > max_rows:
        raise ConstructionLimit("Schreier edges")

    rows = []
    letters = 0
    for permutation, representative in transversal.items():
        for g, generator in enumerate(action.roots, 1):
            target = tuple(generator[x] for x in permutation)
            parent = free(representative + (g,) + inv(transversal[target]))
            if not parent:
                continue
            root, sections = action.wreath(parent)
            require(root == identity, "Schreier parent moves root")
            letters += sum(map(len, sections))
            if letters > max_letters:
                raise ConstructionLimit("section letters")
            rows.append(
                {"parent_word": list(parent), "sections": [list(w) for w in sections]}
            )
    return rows


def prepare(packet, retained_pool):
    """Keep basis and relators; replace the tuple list only after complete enumeration."""
    retained = pool_rows(packet, retained_pool)
    try:
        rows = schreier_rows(Action(packet))
    except ConstructionLimit as limit:
        rows, label, reason = retained, "K", str(limit)
    else:
        label, reason = "H", "complete root Schreier generators"
    return dict(
        retained_pool,
        tuple_generators=rows,
        action_sha256=digest(packet),
        subgroup_label=label,
        selection_reason=reason,
    )
