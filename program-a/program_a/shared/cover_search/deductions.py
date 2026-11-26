"""Lazy exact loop constraints: ambient relators everywhere, K only at row 0."""

from ..exact import inv, free, Limit


def constraints(search):
    P = search.P
    d = search.a.d
    r = len(P.B)
    for i, rel in enumerate(P.relations):
        # TupleImage.add_relation already checked this whole-tree identity.
        for x in range(d):
            yield ("ambient_relator", i, x), [(x, g) for g in rel], None, ()
    for x in range(d):
        for y in range(x + 1, d):
            for i in range(1, r + 1):
                for j in range(1, r + 1):
                    yield ("coordinate_commutation", x, y, i, j), [
                        (x, i),
                        (y, j),
                        (x, -i),
                        (y, -j),
                    ], None, ()
    for i, t in enumerate(P.T, 1):
        value = []
        for x, w in enumerate(t["sections"]):
            value.extend((x, g) for g in P.basis_word(w))
            if len(value) > P.L["word_length"]:
                raise Limit("cover_K_loop_length")
        # r0*t_i=t_i*r0; NOT a relation at all cosets when K is nonnormal.
        yield ("base_K_loop", i), value, 0, (i,)


def scan(search, start, letters, end, desired, kind):
    """Enforce R_start*word=t(desired)*R_end by exact partial path algebra."""
    i = start
    p = ()
    left = 0
    while left < len(letters):
        search.a.tick()
        z = search._edges.get((i, *letters[left]))
        if z is None:
            break
        p = search.proof(p + tuple(z["tuple_word"]))
        i = z["target"]
        left += 1
        search.metrics["deduction_edge_reads"] += 1
    if left == len(letters):
        if i != end:
            search.coincidence(i, end, search.proof(inv(p) + tuple(desired)))
            search.metrics[kind + "_closed_path_coincidences"] += 1
        return
    j = end
    s = ()
    right = len(letters) - 1
    while right > left:
        search.a.tick()
        x, g = letters[right]
        z = search._edges.get((j, x, -g))
        if z is None:
            break
        s = search.proof(s + tuple(z["tuple_word"]))
        j = z["target"]
        right -= 1
        search.metrics["deduction_edge_reads"] += 1
    if left == right:
        # Prefix p, inverse suffix s: k=p^-1*desired*s.
        search.put(
            i, *letters[left], j, search.proof(inv(p) + tuple(desired) + s), kind
        )
        search.metrics[kind + "_one_gap_deductions"] += 1
