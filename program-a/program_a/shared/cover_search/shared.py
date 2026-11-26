"""Batch obligations and bidirectional meet using the EXISTING frontier/residual.

All successful meets become checked K words. Negative lookup cache is only a
generation-scoped search miss, never a nonmembership assertion.
"""

from collections import OrderedDict
from ..exact import free, inv, expand, require, digest, Limit, word
from ..tuples import multiply, inverse


def canonical(t):
    t = tuple(tuple(w) for w in t)
    u = inverse(t)
    return (t, False) if t <= u else (u, True)


class SharedMembership:
    def __init__(self, image, membership, metrics):
        self.P, self.M, self.F, self.a, self.metrics = (
            image,
            membership,
            membership.F,
            image.a,
            metrics,
        )
        self.positive = OrderedDict()
        self.misses = OrderedDict()
        self.goals = OrderedDict()
        self.cache_cap = image.L["cache_entries"]
        self.goal_cap = image.L["residual_target_cap"]
        self.prefix = []
        self.generation = None
        self.goal_cursor = 0

    def refresh(self, check_target=True):
        if check_target:
            now = [tuple(tuple(w) for w in t["sections"]) for t in self.P.T]
            self.metrics["shared_target_prefix_validations"] += 1
            require(
                now[: len(self.prefix)] == self.prefix,
                "Finite-cover K may only append; old proof symbols must stay fixed",
            )
            if len(now) != len(self.prefix):
                self.prefix = now
                self.misses.clear()
                for g in self.goals.values():
                    g["meet_cursor"] = 1
                self.metrics["shared_K_growth_invalidations"] += 1
        generation = (len(self.P.T), self.F.version, len(self.M.proofs))
        if generation != self.generation:
            self.misses.clear()
            # New frontier entries may satisfy meets against old suffixes.
            for g in self.goals.values():
                g["meet_cursor"] = 1
            self.generation = generation
            self.metrics["shared_search_generation_updates"] += 1

    def record(self, t, w, *, check=False):
        w = free(w)
        if len(w) > self.P.L["word_length"]:
            raise Limit("cover_shared_proof_word_length")
        if check:
            self.M.prove(t, w)
        key, reversed_ = canonical(t)
        w = inv(w) if reversed_ else w
        if len(self.positive) >= self.cache_cap and key not in self.positive:
            self.positive.popitem(last=False)
        self.positive[key] = w
        self.misses.pop(key, None)
        return w

    def lookup(self, t):
        self.metrics["shared_lookup_requests"] += 1
        key, reversed_ = canonical(t)
        if key in self.positive:
            self.metrics["shared_positive_cache_hits"] += 1
            self.metrics["shared_inverse_positive_hits"] += reversed_
            w = self.positive[key]
            return inv(w) if reversed_ else w
        if key in self.misses:
            # F.lookup has a resumable partial bucket cursor even when version
            # is static. A miss is throttled, never permanently memoized.
            self.misses[key] += 1
            if self.misses[key] % 4:
                self.metrics["shared_generation_miss_hits"] += 1
                return None
            self.metrics["shared_fair_partial_lookup_retries"] += 1
        self.metrics["shared_underlying_lookup_calls"] += 1
        w = self.M.lookup(key)
        if w is None:
            self.metrics["shared_underlying_lookup_calls"] += 1
            back = self.M.lookup(inverse(key))
            if back is not None:
                w = inv(back)
                self.metrics["shared_inverse_underlying_hits"] += 1
        if w is not None:
            self.record(key, w)
            return inv(w) if reversed_ else w
        if len(self.misses) >= self.cache_cap:
            self.misses.popitem(last=False)
        self.misses[key] = 0
        return None

    def request(self, t, consumer, benefit):
        key, _ = canonical(t)
        if key in self.positive:
            return
        if key in self.goals:
            g = self.goals[key]
            g["benefit"] = min(g["benefit"], benefit)
            if consumer not in g["consumers"] and len(g["consumers"]) < 16:
                g["consumers"].append(consumer)
                g["requests"] += 1
                self.metrics["shared_cross_gap_obligation_reuses"] += 1
            else:
                self.metrics["shared_repeated_same_goal_requests"] += 1
            return
        if len(self.goals) >= self.goal_cap:
            self.metrics["shared_goal_cap_deferrals"] += 1
            return
        self.goals[key] = {
            "benefit": benefit,
            "requests": 1,
            "meet_cursor": 1,
            "consumers": [consumer],
        }
        before = len(self.M.targets)
        self.M.add(key, "finite_cover_shared_batch")
        self.metrics["shared_actual_residual_registrations"] += (
            len(self.M.targets) - before
        )
        if hasattr(self.M, "prioritize"):
            self.M.prioritize(key, benefit)
        self.metrics["shared_unique_obligations"] += 1

    def work(self, count, *, checked=False):
        self.refresh(check_target=not checked)
        if not self.goals:
            return 0
        # These are actual API calls/work deltas, not renamed prior counters.
        n = max(1, count // 3)
        before_f = dict(self.F.metrics)
        before_m = dict(self.M.metrics)
        units = self.M.step(n)
        self.metrics["shared_residual_step_units"] += units
        polls = self.F.grow(min(4, self.P.L["residual_depth"]), n)
        self.metrics["shared_frontier_poll_units"] += polls or 0
        for key in ["residual_nodes", "expanded_states"]:
            self.metrics["shared_actual_" + key] += self.M.metrics[key] - before_m.get(
                key, 0
            )
        for key in ["product_attempts", "product_nodes"]:
            self.metrics["shared_actual_" + key] += self.F.metrics[key] - before_f.get(
                key, 0
            )
        self.refresh(check_target=False)
        done = 0
        for _ in range(max(1, count - 2 * n)):
            if not self.goals:
                break
            keys = list(self.goals)
            # Every fourth goal is base-order, others favor multiple consumers.
            if self.goal_cursor % 4 == 3:
                key = keys[(self.goal_cursor // 4) % len(keys)]
            else:
                key = min(
                    keys,
                    key=lambda k: (
                        self.goals[k]["benefit"],
                        -self.goals[k]["requests"],
                        k,
                    ),
                )
            self.goal_cursor += 1
            goal = self.goals[key]
            if self.lookup(key) is not None:
                del self.goals[key]
                self.metrics["shared_completed_obligations"] += 1
                continue
            if goal["meet_cursor"] >= len(self.F.nodes):
                self.metrics["shared_meet_cursor_waits"] += 1
                continue
            suffix, suffix_word = self.F.nodes[goal["meet_cursor"]]
            goal["meet_cursor"] += 1
            target = multiply(key, suffix)
            self.metrics["shared_bidirectional_meet_probes"] += 1
            done += 1
            self.metrics["shared_underlying_lookup_calls"] += 1
            prefix = self.F.lookup(target)
            if prefix is not None:
                # key*suffix=prefix, hence key=prefix*suffix^-1.
                proof = free(tuple(prefix) + inv(suffix_word))
                self.record(key, proof, check=True)
                self.metrics["shared_bidirectional_meet_successes"] += 1
                del self.goals[key]
        return done + units + (polls or 0)

    def export(self):
        return {
            "K_count": len(self.prefix),
            "K_prefix_sha256": digest(self.prefix),
            "goal_cursor": self.goal_cursor,
            "positive": [
                [[list(w) for w in t], list(v)] for t, v in self.positive.items()
            ],
            "goals": [
                [
                    [list(w) for w in t],
                    {**g, "consumers": [list(c) for c in g["consumers"]]},
                ]
                for t, g in self.goals.items()
            ],
            "native_state_saved": False,
        }

    def restore(self, z):
        n = z["K_count"]
        require(type(n) is int and 0 <= n <= len(self.P.T), "Cover shared K count")
        prefix = [tuple(tuple(w) for w in t["sections"]) for t in self.P.T[:n]]
        require(
            digest(prefix) == z["K_prefix_sha256"],
            "Cover shared K/alphabet checkpoint changed",
        )
        require(
            z.get("native_state_saved") is False,
            "No native state exists in a cover checkpoint",
        )
        require(
            len(z["positive"]) <= self.cache_cap and len(z["goals"]) <= self.goal_cap,
            "Cover shared checkpoint cap",
        )
        require(
            type(z["goal_cursor"]) is int and 0 <= z["goal_cursor"] < 2**63,
            "Shared goal cursor",
        )
        self.refresh()

        def target(t):
            require(
                type(t) is list and len(t) == self.a.d, "Shared checkpoint tuple degree"
            )
            return tuple(
                word(
                    v,
                    self.a.q,
                    self.P.L["word_length"],
                    "Shared checkpoint original word",
                )
                for v in t
            )

        for t, w in z["positive"]:
            word(w, len(self.P.T), self.P.L["word_length"], "Shared checkpoint K word")
            self.record(target(t), w, check=True)
        for t, g in z["goals"]:
            require(
                type(g["benefit"]) is int
                and 1 <= g["benefit"] <= self.a.d * 2 * len(self.P.B),
                "Shared benefit",
            )
            require(
                type(g["requests"]) is int and 1 <= g["requests"] <= 16,
                "Shared distinct consumer count",
            )
            consumers = g["consumers"]
            require(
                type(consumers) is list and len(consumers) == g["requests"],
                "Shared consumers",
            )
            for c in consumers:
                require(
                    type(c) in (list, tuple)
                    and 1 <= len(c) <= 6
                    and all(
                        type(v) is int
                        and abs(v) < 2**31
                        or type(v) is str
                        and len(v) <= 64
                        for v in c
                    ),
                    "Shared consumer shape",
                )
            consumers = [tuple(c) for c in consumers]
            require(
                len(set(consumers)) == len(consumers),
                "Shared consumers must be distinct",
            )
            key, _ = canonical(target(t))
            self.request(key, consumers[0], g["benefit"])
            if key in self.goals:
                require(
                    type(g["meet_cursor"]) is int and 0 <= g["meet_cursor"] < 2**63,
                    "Shared meet cursor",
                )
                self.goals[key]["meet_cursor"] = min(
                    g["meet_cursor"], len(self.F.nodes)
                )
                self.goals[key]["requests"] = g["requests"]
                self.goals[key]["consumers"] = consumers
        self.goal_cursor = z["goal_cursor"]
