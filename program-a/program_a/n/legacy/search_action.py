"""Search caches only. Final certificates use the unchanged frozen verifier."""

from ...shared.weak_verify import Action


class SearchAction(Action):
    def __init__(self, packet, L):
        super().__init__(packet, L)
        self.metrics = {
            "identity_queries": 0,
            "identity_cache_hits": 0,
            "fingerprint_queries": 0,
            "fingerprint_cache_hits": 0,
            "decomposition_queries": 0,
            "decomposition_cache_hits": 0,
        }
        self.fp_cache = {}
        self.decomp_cache = {}
        self.search_cache_cap = L.get("search_cache_cap", 100000)

    def identity(self, w):
        self.tick()
        w = self.reduce(w)
        self.metrics["identity_queries"] += 1
        if w in self.cache:
            self.metrics["identity_cache_hits"] += 1
        result = super().identity(w)
        if len(self.cache) > self.search_cache_cap:
            self.cache.clear()
        return result

    def fingerprint(self, w, depth=3):
        self.tick()
        w = self.reduce(w)
        key = (w, depth)
        self.metrics["fingerprint_queries"] += 1
        if key in self.fp_cache:
            self.metrics["fingerprint_cache_hits"] += 1
            return self.fp_cache[key]
        ans = super().fingerprint(w, depth)
        if len(self.fp_cache) >= self.search_cache_cap:
            self.fp_cache.clear()
        self.fp_cache[key] = ans
        return ans

    def decompose(self, w):
        self.tick()
        w = self.reduce(w)
        self.metrics["decomposition_queries"] += 1
        if w in self.decomp_cache:
            self.metrics["decomposition_cache_hits"] += 1
            return self.decomp_cache[w]
        steps = tuple(self.step(w, x) for x in range(self.d))
        ans = (tuple(t[0] for t in steps), tuple(t[1] for t in steps))
        if len(self.decomp_cache) >= self.search_cache_cap:
            self.decomp_cache.clear()
        self.decomp_cache[w] = ans
        return ans

    def root(self, w):
        return self.decompose(w)[0]
