"""Closed finite-root Schreier edges and root-order powers: seed words, not an index claim."""

from collections import deque
from ..shared.weak_verify import inv, expand


def root_seeds(a, B, L):
    identity = tuple(range(a.d))
    states = [identity]
    reps = [()]
    seen = {identity: 0}
    queue = deque([0])
    letters = tuple(range(1, len(B) + 1)) + tuple(range(-len(B), 0))
    roots = {g: a.root(expand((g,), B)) for g in letters}
    emitted = 0
    for g in range(1, len(B) + 1):
        perm = identity
        for power in range(1, 257):
            a.tick()
            perm = tuple(roots[g][perm[x]] for x in range(a.d))
            if perm == identity:
                yield expand((g,) * power, B)
                break
    while queue and emitted < L["tuple_cap"]:
        i = queue.popleft()
        for g in letters:
            a.tick()
            s = tuple(roots[g][states[i][x]] for x in range(a.d))
            if s not in seen and len(states) < 128:
                seen[s] = len(states)
                states.append(s)
                reps.append(reps[i] + (g,))
                queue.append(seen[s])
            if s in seen:
                w = reps[i] + (g,) + inv(reps[seen[s]])
                if w:
                    yield expand(w, B)
                    emitted += 1
            if emitted >= min(512, L["tuple_cap"]):
                return
