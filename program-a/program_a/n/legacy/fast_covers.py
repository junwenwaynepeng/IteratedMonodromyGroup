"""Same formal finite covers; fingerprint rejection before exact generator deduplication."""

from collections import deque
from math import gcd, prod
from ...shared.weak_verify import expand, inv, Limit
from . import cover_tools as tools


class EqualityIndex:
    def __init__(self, a):
        self.a = a
        self.depth = 3
        while a.d**self.depth > 128:
            self.depth -= 1
        self.by = {}

    def find(self, raw, N):
        f = self.a.fingerprint(raw, self.depth)
        for k, sign in self.by.get(f, []):
            self.a.metrics["cover_exact_equality_checks"] = (
                self.a.metrics.get("cover_exact_equality_checks", 0) + 1
            )
            n = N[k - 1] if sign > 0 else inv(N[k - 1])
            if self.a.equal(raw, n):
                return k * sign
        return None

    def add(self, raw, k):
        f = self.a.fingerprint(raw, self.depth)
        fi = [0] * len(f)
        for i, j in enumerate(f):
            fi[j] = i
        self.by.setdefault(f, []).append((k, 1))
        self.by.setdefault(tuple(fi), []).append((k, -1))


class FastCover:
    def __init__(self, a, B, kind, cap):
        self.a = a
        self.B = B
        self.r = len(B)
        self.kind = kind
        self.reps = [()]
        self.states = [
            (
                (0,) * len(B)
                if (
                    kind.startswith("universal_mod_")
                    or kind.startswith("universal_mixed_")
                )
                else (
                    0
                    if kind in ("involution_derived", "root_sign_kernel")
                    else tuple(range(a.d))
                )
            )
        ]
        self.edges = {}
        self.N = []
        self.Nbasis = []
        self.transitions = {}
        self.index = EqualityIndex(a)
        rootgens = [a.root(w) for w in B]

        def transition(s, g):
            if kind.startswith("universal_mixed_"):
                moduli = tuple(map(int, kind[len("universal_mixed_") :].split("_")))
                v = list(s)
                v[abs(g) - 1] = (v[abs(g) - 1] + (1 if g > 0 else -1)) % moduli[
                    abs(g) - 1
                ]
                return tuple(v)
            if kind.startswith("universal_mod_"):
                modulus = int(kind.rsplit("_", 1)[1])
                v = list(s)
                v[abs(g) - 1] = (v[abs(g) - 1] + (1 if g > 0 else -1)) % modulus
                return tuple(v)
            if kind == "involution_derived":
                return s ^ (1 << (abs(g) - 1))
            if kind == "root_sign_kernel":
                p = rootgens[abs(g) - 1]
                return s ^ (
                    sum(p[i] > p[j] for i in range(a.d) for j in range(i + 1, a.d)) % 2
                )
            p = rootgens[abs(g) - 1]
            if g < 0:
                p = tuple(p.index(x) for x in range(a.d))
            return tuple(p[s[x]] for x in range(a.d))

        self.transition = transition
        state_index = {self.states[0]: 0}
        queue = deque([0])
        letters = list(range(1, self.r + 1)) + list(range(-self.r, 0))
        while queue:
            i = queue.popleft()
            for g in letters:
                s = transition(self.states[i], g)
                if s not in state_index:
                    if len(self.states) >= cap:
                        raise Limit("coset_cap")
                    state_index[s] = len(self.states)
                    self.states.append(s)
                    self.reps.append(self.reps[i] + (g,))
                    queue.append(len(self.states) - 1)
                j = state_index[s]
                self.transitions[i, g] = j
        for i in range(len(self.reps)):
            for g in letters:
                j = self.transitions[i, g]
                v = self.reps[i] + (g,) + inv(self.reps[j])
                raw = expand(v, B)
                if a.identity(raw):
                    self.edges[i, g] = 0
                    continue
                found = self.index.find(raw, self.N)
                if found is None:
                    self.N.append(raw)
                    self.Nbasis.append(v)
                    found = len(self.N)
                    self.index.add(raw, found)
                    if found > a.limits.get("candidate_N_cap", 100000):
                        raise Limit("candidate_N_cap")
                self.edges[i, g] = found

    def rewrite(self, w):
        i = 0
        out = []
        for g in w:
            k = self.edges[i, g]
            if k:
                out.append(k)
            i = self.transitions[i, g]
        if i:
            raise ValueError("Formal cover endpoint not identity")
        return out

    def certificate(self, original):
        letters = list(range(1, self.r + 1)) + list(range(-self.r, 0))
        return {
            "schema_version": 1,
            "basis_words": self.B,
            "original_generator_words": original,
            "N_generators": self.N,
            "coset_cover": {
                "representatives": [expand(t, self.B) for t in self.reps],
                "transitions": [
                    {
                        "coset": i,
                        "letter": g,
                        "target": self.transitions[i, g],
                        "N_word": [self.edges[i, g]] if self.edges[i, g] else [],
                    }
                    for i in range(len(self.reps))
                    for g in letters
                ],
            },
            "normality": [
                {
                    "N_generator": i,
                    "letter": g,
                    "N_word": self.rewrite((-g,) + n + (g,)),
                }
                for i, n in enumerate(self.Nbasis, 1)
                for g in letters
            ],
            "supported_lifts": [],
        }


class FastClass2Cover:
    def __init__(self, a, B, m, cap=512):
        self.a = a
        self.B = B
        self.r = len(B)
        self.m = m
        self.kind = "class2_mod_" + str(m)
        self.pairs = [(i, j) for i in range(self.r) for j in range(i + 1, self.r)]
        size = m ** (self.r + len(self.pairs))
        if size > cap:
            raise Limit("class2_coset_cap")
        self.states = [(0,) * (self.r + len(self.pairs))]
        self.reps = [()]
        self.transitions = {}
        self.edges = {}
        self.N = []
        self.Nbasis = []
        self.index = EqualityIndex(a)
        indices = {self.states[0]: 0}
        q = deque([0])
        letters = list(range(1, self.r + 1)) + list(range(-self.r, 0))
        while q:
            i = q.popleft()
            for g in letters:
                a.tick()
                s = self.multiply_generator(self.states[i], g)
                if s not in indices:
                    indices[s] = len(self.states)
                    self.states.append(s)
                    self.reps.append(self.reps[i] + (g,))
                    q.append(indices[s])
                self.transitions[i, g] = indices[s]
        assert len(self.states) == size
        for i in range(size):
            for g in letters:
                a.tick()
                j = self.transitions[i, g]
                w = self.reps[i] + (g,) + inv(self.reps[j])
                raw = expand(w, B)
                if a.identity(raw):
                    self.edges[i, g] = 0
                    continue
                k = self.index.find(raw, self.N)
                if k is None:
                    self.N.append(raw)
                    self.Nbasis.append(w)
                    k = len(self.N)
                    self.index.add(raw, k)
                    if k > a.limits.get("candidate_N_cap", 100000):
                        raise Limit("candidate_N_cap")
                self.edges[i, g] = k

    def multiply_generator(self, state, g):
        i = abs(g) - 1
        sgn = 1 if g > 0 else -1
        out = list(state)
        for k, (u, v) in enumerate(self.pairs):
            if u == i:
                out[self.r + k] = (out[self.r + k] - sgn * state[v]) % self.m
        out[i] = (out[i] + sgn) % self.m
        return tuple(out)

    def rewrite(self, w):
        current = 0
        answer = []
        for g in w:
            k = self.edges[current, g]
            if k:
                answer.append(k)
            current = self.transitions[current, g]
        if current:
            raise ValueError("Not in formal class2 cover kernel")
        return answer

    def certificate(self, original):
        letters = list(range(1, self.r + 1)) + list(range(-self.r, 0))
        return {
            "schema_version": 1,
            "basis_words": self.B,
            "original_generator_words": original,
            "N_generators": self.N,
            "coset_cover": {
                "representatives": [expand(t, self.B) for t in self.reps],
                "transitions": [
                    {
                        "coset": i,
                        "letter": g,
                        "target": self.transitions[i, g],
                        "N_word": [self.edges[i, g]] if self.edges[i, g] else [],
                    }
                    for i in range(len(self.reps))
                    for g in letters
                ],
            },
            "normality": [
                {
                    "N_generator": i,
                    "letter": g,
                    "N_word": self.rewrite((-g,) + n + (g,)),
                }
                for i, n in enumerate(self.Nbasis, 1)
                for g in letters
            ],
            "supported_lifts": [],
        }


class FastMixedClass2Cover:
    def __init__(self, a, B, m, cap=512):
        self.a = a
        self.B = B
        self.r = len(B)
        self.moduli = tuple(m)
        assert len(m) == self.r and all(n >= 2 for n in m)
        self.kind = "mixed_class2_" + "_".join(map(str, m))
        self.pairs = [(i, j) for i in range(self.r) for j in range(i + 1, self.r)]
        self.central = [gcd(m[i], m[j]) for i, j in self.pairs]
        size = prod(m) * prod(self.central)
        if size > cap:
            raise Limit("class2_coset_cap")
        self.states = [(0,) * (self.r + len(self.pairs))]
        self.reps = [()]
        self.transitions = {}
        self.edges = {}
        self.N = []
        self.Nbasis = []
        self.index = EqualityIndex(a)
        indices = {self.states[0]: 0}
        q = deque([0])
        letters = list(range(1, self.r + 1)) + list(range(-self.r, 0))
        while q:
            i = q.popleft()
            for g in letters:
                a.tick()
                s = self.multiply_generator(self.states[i], g)
                if s not in indices:
                    indices[s] = len(self.states)
                    self.states.append(s)
                    self.reps.append(self.reps[i] + (g,))
                    q.append(indices[s])
                self.transitions[i, g] = indices[s]
        assert len(self.states) == size
        for i in range(size):
            for g in letters:
                a.tick()
                j = self.transitions[i, g]
                w = self.reps[i] + (g,) + inv(self.reps[j])
                raw = expand(w, B)
                if a.identity(raw):
                    self.edges[i, g] = 0
                    continue
                k = self.index.find(raw, self.N)
                if k is None:
                    self.N.append(raw)
                    self.Nbasis.append(w)
                    k = len(self.N)
                    self.index.add(raw, k)
                    if k > a.limits.get("candidate_N_cap", 100000):
                        raise Limit("candidate_N_cap")
                self.edges[i, g] = k

    def multiply_generator(self, state, g):
        i = abs(g) - 1
        sgn = 1 if g > 0 else -1
        out = list(state)
        for k, (u, v) in enumerate(self.pairs):
            if u == i:
                out[self.r + k] = (out[self.r + k] - sgn * state[v]) % self.central[k]
        out[i] = (out[i] + sgn) % self.moduli[i]
        return tuple(out)

    def rewrite(self, w):
        current = 0
        answer = []
        for g in w:
            k = self.edges[current, g]
            if k:
                answer.append(k)
            current = self.transitions[current, g]
        if current:
            raise ValueError("Not in formal class2 cover kernel")
        return answer

    def certificate(self, original):
        letters = list(range(1, self.r + 1)) + list(range(-self.r, 0))
        return {
            "schema_version": 1,
            "basis_words": self.B,
            "original_generator_words": original,
            "N_generators": self.N,
            "coset_cover": {
                "representatives": [expand(t, self.B) for t in self.reps],
                "transitions": [
                    {
                        "coset": i,
                        "letter": g,
                        "target": self.transitions[i, g],
                        "N_word": [self.edges[i, g]] if self.edges[i, g] else [],
                    }
                    for i in range(len(self.reps))
                    for g in letters
                ],
            },
            "normality": [
                {
                    "N_generator": i,
                    "letter": g,
                    "N_word": self.rewrite((-g,) + n + (g,)),
                }
                for i, n in enumerate(self.Nbasis, 1)
                for g in letters
            ],
            "supported_lifts": [],
        }
