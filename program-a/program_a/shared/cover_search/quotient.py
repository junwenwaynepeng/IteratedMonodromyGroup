"""Exact finite tree-action homomorphism and COMPLETE q(K) right cosets.

Different q(K)q(r) cosets exclude equality. Equal cosets prove nothing in K.
Incomplete closure is never used as a negative filter.
"""

from collections import deque
from ..exact import require, digest


class ConstructionBound(Exception):
    pass


def perm_product(a, b):
    return tuple(b[x] for x in a)  # right action: first a, then b


def perm_inverse(a):
    out = [0] * len(a)
    for x, y in enumerate(a):
        out[y] = x
    return tuple(out)


def product(a, b):
    return tuple(perm_product(x, y) for x, y in zip(a, b))


def inverse(a):
    return tuple(perm_inverse(x) for x in a)


class FiniteCosets:
    def __init__(self, image, metrics, *, max_elements=None, max_work=None, depth=None):
        self.P, self.a, self.metrics = image, image.a, metrics
        self.depth = depth or (2 if image.a.d**2 <= 16 else 1)
        self.points = image.a.d**self.depth
        self.max_elements = max_elements or min(
            256, image.L.get("root_seed_states", 128), image.L["frontier_cap"]
        )
        self.max_work = max_work or min(20000, image.L["frontier_total_letters"])
        self.cache_cap = min(image.L["cache_entries"], image.L["residual_target_cap"])
        self.signature = None
        self.disabled_reason = "NOT_BUILT"
        self._stamp = None
        self.subgroup = None
        self.buckets = {}
        self.word_cache = {}
        self.generators = {}
        self.version = 0
        self._work = 0
        self.one = tuple(range(self.points))
        self.identity = tuple(self.one for _ in range(image.a.d))

    def charge(self, n=1):
        self.a.tick()
        self._work += n
        self.metrics["quotient_budget_charges"] += n
        if self._work > self.max_work:
            raise ConstructionBound("QUOTIENT_WORK_BOUND")

    def letter(self, g):
        if g in self.generators:
            return self.generators[g]
        self.charge(self.points * self.depth)
        perm = []
        d = self.a.d
        for number in range(self.points):
            value = number
            out = 0
            place = 1
            section = (g,)
            for _ in range(self.depth):
                x = value % d
                value //= d
                y, section = self.a.step(section, x)
                out += place * y
                place *= d
            perm.append(out)
        require(
            sorted(perm) == list(range(self.points)),
            "Finite quotient generator must be a permutation",
        )
        ans = tuple(perm)
        self.generators[g] = ans
        self.generators[-g] = perm_inverse(ans)
        self.metrics["quotient_exact_generator_permutations"] += 1
        return ans

    def word(self, w):
        key = tuple(w)
        if key in self.word_cache:
            return self.word_cache[key]
        p = self.one
        for g in w:
            self.charge(self.points)
            p = perm_product(p, self.letter(g))
        if len(self.word_cache) >= self.cache_cap:
            self.word_cache.pop(next(iter(self.word_cache)))
        self.word_cache[key] = p
        return p

    def image(self, t):
        return tuple(self.word(w) for w in t)

    def disable(self, reason):
        self.subgroup = None
        self.buckets.clear()
        self.disabled_reason = reason
        self.metrics["quotient_fallbacks"] += 1

    def refresh(self):
        stamp = (len(self.P.T), self.P.version)
        if stamp == self._stamp:
            return
        self._stamp = stamp
        signature = digest([t["sections"] for t in self.P.T])
        if signature == self.signature:
            return
        self.signature = signature
        self.version += 1
        self.buckets.clear()
        self._work = 0
        # Never leave an older (smaller) q(K) active during a rebuild/interrupt.
        self.subgroup = None
        self.disabled_reason = "QUOTIENT_BUILD_INCOMPLETE"
        self.metrics["quotient_K_rebuilds"] += 1
        try:
            if self.points > 64:
                raise ConstructionBound("QUOTIENT_DEGREE_BOUND")
            # Check the entire actual generator list before using its closure.
            if len(self.P.T) * self.a.d > self.max_work:
                raise ConstructionBound("QUOTIENT_INPUT_BOUND")
            gens = set()
            for t in self.P.T:
                v = self.image(t["sections"])
                if v != self.identity:
                    gens.add(v)
                    gens.add(inverse(v))
            seen = {self.identity}
            queue = deque([self.identity])
            while queue:
                h = queue.popleft()
                for g in sorted(gens):
                    self.charge(self.a.d * self.points)
                    v = product(h, g)
                    if v not in seen:
                        if len(seen) >= self.max_elements:
                            raise ConstructionBound("QUOTIENT_SUBGROUP_ORDER_BOUND")
                        seen.add(v)
                        queue.append(v)
            # q(K)=q(Gamma^d) iff it contains all coordinate basis images.
            useful = False
            for x in range(self.a.d):
                for w in self.P.B:
                    v = list(self.identity)
                    v[x] = self.word(w)
                    if tuple(v) not in seen:
                        useful = True
            if not useful:
                raise ConstructionBound("QUOTIENT_USELESS_FULL_AMBIENT_IMAGE")
            self.subgroup = tuple(sorted(seen))
            self.disabled_reason = None
            self.metrics["quotient_complete_closures"] += 1
            self.metrics["quotient_subgroup_order"] = len(seen)
        except ConstructionBound as e:
            self.disable(str(e))

    def bucket(self, t):
        # The cover refreshes once per quantum after append-only validation.
        # Rehashing all of T per representative/query is deliberately avoided.
        if self.signature is None:
            self.refresh()
        if self.subgroup is None:
            return None
        key = tuple(tuple(w) for w in t)
        if key in self.buckets:
            return self.buckets[key]
        # Query work is separately bounded; no incomplete coset minimum is used.
        self._work = 0
        try:
            qt = self.image(t)
            values = []
            for k in self.subgroup:
                self.charge(self.a.d * self.points)
                values.append(product(k, qt))
            ans = min(values)
            if len(self.buckets) >= self.cache_cap:
                self.buckets.pop(next(iter(self.buckets)))
            self.buckets[key] = ans
            self.metrics["quotient_coset_buckets"] += 1
            return ans
        except ConstructionBound as e:
            self.disable(str(e))
            return None

    def different(self, u, v):
        a, b = self.bucket(u), self.bucket(v)
        different = a is not None and b is not None and a != b
        self.metrics["quotient_coset_rejections"] += different
        return different

    def summary(self):
        return {
            "depth": self.depth,
            "points": self.points,
            "K_version": self.version,
            "complete_qK_order": (
                len(self.subgroup) if self.subgroup is not None else None
            ),
            "fallback_reason": self.disabled_reason,
            "positive_membership_proof": False,
        }
