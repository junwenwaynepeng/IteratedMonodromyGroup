"""EXPERIMENTAL standalone direct-image finite-cover checker, not Program A runtime.
No discovery/search: raw signed-state whole-tree identity replay, free cancellation
only; no finite-depth signatures, Action canonicalizer, geometry or expected I.
"""

import time
from collections import deque


def inv(w):
    return [-g for g in reversed(w)]


def free(w):
    s = []
    for g in w:
        if s and s[-1] == -g:
            s.pop()
        else:
            s.append(g)
    return tuple(s)


def expand(w, B):
    return [g for i in w for g in (B[i - 1] if i > 0 else inv(B[-i - 1]))]


class CheckLimit(Exception):
    pass


class Raw:
    def __init__(self, packet, seconds=10, states=10000):
        m = packet.get("model", packet)
        self.roots = m["roots"]
        self.sections = m["sections"]
        self.q = len(self.roots)
        self.d = len(self.roots[0])
        self.end = time.monotonic() + seconds
        self.cap = states
        self.cache = {}
        self.calls = 0
        self.visited = 0
        self.max_word = 0
        self.steps = 0

    def word(self, w, rank=None):
        assert isinstance(w, (list, tuple)) and all(
            type(i) is int and 0 < abs(i) <= (rank or self.q) for i in w
        )

    def step(self, w, x):
        sec = []
        for g in w:
            i = abs(g) - 1
            if g > 0:
                y = self.roots[i][x]
                s = self.sections[i][x]
            else:
                y = self.roots[i].index(x)
                s = -self.sections[i][y]
            if s:
                sec.append(s)
            x = y
            self.steps += 1
        return x, free(sec)

    def identity(self, w):
        self.calls += 1
        w = free(w)
        self.max_word = max(self.max_word, len(w))
        if w in self.cache:
            return self.cache[w]
        pending = deque([w])
        seen = set()
        while pending:
            if time.monotonic() >= self.end:
                raise CheckLimit("wallclock_seconds")
            u = pending.popleft()
            if u in seen or self.cache.get(u) is True:
                continue
            seen.add(u)
            if len(seen) > self.cap:
                raise CheckLimit("identity_states")
            for x in range(self.d):
                y, s = self.step(u, x)
                if y != x:
                    self.cache[w] = False
                    return False
                if s and s not in seen:
                    pending.append(s)
        for u in seen:
            self.cache[u] = True
        self.visited += len(seen)
        return True

    def equal(self, u, v):
        return self.identity(list(u) + inv(v))


def verify(packet, c, seconds=10, states=10000):
    a = Raw(packet, seconds, states)
    try:
        B = c["basis_words"]
        original = c["original_generator_words"]
        assert B and len(original) == a.q
        for b in B:
            a.word(b)
        for g, w in enumerate(original, 1):
            a.word(w, len(B))
            assert a.equal(expand(w, B), [g]), ("basis", g)
        T = c["tuple_generators"]
        R = c["coset_representatives"]
        q = len(R)
        assert q > 0 and T
        for t in T:
            a.word(t["parent_word"])
            assert len(t["sections"]) == a.d
            for x, w in enumerate(t["sections"]):
                a.word(w)
                y, s = a.step(t["parent_word"], x)
                assert y == x and a.equal(s, w), ("tuple_parent", x)
        for r in R:
            assert len(r) == a.d
            for w in r:
                a.word(w)
        assert all(a.identity(w) for w in R[0]), "Identity representative required"
        transitions = {}
        for z in c["transitions"]:
            key = z["coset"], z["child"], z["letter"]
            assert key not in transitions
            transitions[key] = z
        letters = list(range(1, len(B) + 1)) + list(range(-len(B), 0))
        assert set(transitions) == {
            (i, x, g) for i in range(q) for x in range(a.d) for g in letters
        }, "Complete signed transition table required"
        for (i, x, g), z in transitions.items():
            j = z["target"]
            assert type(j) is int and 0 <= j < q
            a.word(z["tuple_word"], len(T))
            # c_i * coordinate(x,g) = tuple_word(T) * c_j (right coset orientation).
            for y in range(a.d):
                lhs = (
                    list(R[i][y]) + (list(B[g - 1]) if g > 0 else inv(B[-g - 1]))
                    if y == x
                    else list(R[i][y])
                )
                k = [
                    h
                    for n in z["tuple_word"]
                    for h in (
                        T[n - 1]["sections"][y]
                        if n > 0
                        else inv(T[-n - 1]["sections"][y])
                    )
                ]
                rhs = k + list(R[j][y])
                assert a.equal(lhs, rhs), ("cover_transition", i, x, g, y)
        return {
            "status": "PASS_DIRECT_IMAGE_BOUND",
            "I_upper_bound": q,
            "valid_n_min": 1,
            "cover_size_is_exact_index": False,
            "tuple_generators": len(T),
            "signed_transitions": len(transitions),
            "scope": "K generated by verified tuples lies in H; [G^d:H]<=q. Experimental checker, not integrated/reviewed Program A runtime.",
            "raw_identity_calls": a.calls,
            "closed_graph_states_total": a.visited,
            "maximum_raw_word_length": a.max_word,
            "raw_letter_steps": a.steps,
        }
    except CheckLimit as e:
        return {"status": "UNKNOWN", "reason": str(e)}
    except Exception as e:
        return {"status": "FAIL", "reason": repr(e)}
