"""Proof-carrying finite-cover search. No K normality assumption or target change."""

import time
from collections import Counter, OrderedDict
from ..exact import free, inv, expand, require, Limit, digest, word
from ..tuples import multiply, inverse
from .quotient import FiniteCosets
from .shared import SharedMembership
from .deductions import constraints, scan


class CoverSearch:
    def __init__(self, image, membership, lower_bound=1, clock=time.monotonic):
        self.P, self.M, self.a = image, membership, image.a
        self.R = [tuple(() for _ in range(self.a.d))]
        self.Z = []
        self.edge = 0
        self.j = 0
        self.cursor = 0
        self.lower_bound = max(1, int(lower_bound))
        self.goal = min(image.L["small_cover_rows_max"], max(2, self.lower_bound))
        self.clock, self.last_growth = clock, clock()
        self.rounds = 0
        self.merge_i, self.merge_j = 1, 0
        self.generation = None
        self.metrics = Counter()
        self._keys = set()
        self._edges = {}
        self._filled = Counter()
        self._coincidences = OrderedDict()
        self._blocked_conflict = None
        self._attempts = OrderedDict()
        self._priority_cursor = 0
        self._schedule_turn = 0
        self._scan_iterator = None
        self._scan_offset = 0
        self._scan_signature = None
        self._in_step = False
        self._scope = digest({"model": self.a.m, "B": self.P.B, "G": self.P.G})
        self.shared = SharedMembership(image, membership, self.metrics)
        self.quotient = FiniteCosets(image, self.metrics)

    @property
    def letters(self):
        r = len(self.P.B)
        return tuple(range(1, r + 1)) + tuple(range(-r, 0))

    @property
    def width(self):
        return self.a.d * len(self.letters)

    def proof(self, w):
        w = free(w)
        if len(w) > self.P.L["word_length"]:
            raise Limit("cover_proof_word_length")
        return w

    def summary(self):
        total = len(self.R) * self.width
        return {
            "candidate_rows": len(self.R),
            "current_small_row_goal": self.goal,
            "recorded_transitions": len(self.Z),
            "slots_for_current_rows": total,
            "unfilled_current_slots": total - len(self.Z),
            "metrics": dict(self.metrics),
            "pending_coincidences": len(self._coincidences),
            "finite_quotient": self.quotient.summary(),
            "qualification": "Witnessed upper-bound candidate only; quotient equality/search miss proves no K membership or distinctness.",
        }

    def coincidence(self, i, j, c):
        """Queue R_i=t(c)R_j; every conflicting target remains represented."""
        c = self.proof(c)
        if i == j:
            return
        if i < j:
            i, j, c = j, i, inv(c)
        if (i, j) in self._coincidences:
            return
        cap = min(self.P.L["cache_entries"], self.P.L["frontier_cap"])
        if len(self._coincidences) >= cap:
            self._blocked_conflict = (i, j, c)
            raise Limit("cover_coincidence_queue_cap")
        self._coincidences[i, j] = c
        self.metrics["witnessed_coincidences_queued"] += 1

    def _put(self, i, x, g, j, w, kind):
        key = i, x, g
        w = self.proof(w)
        if key in self._edges:
            old = self._edges[key]
            if old["target"] != j:
                # u R_p = w R_j => R_p=u^-1*w R_j.
                self.coincidence(
                    old["target"], j, self.proof(inv(old["tuple_word"]) + w)
                )
                self.metrics["edge_target_conflicts_preserved"] += 1
            return False
        z = {"coset": i, "child": x, "letter": g, "target": j, "tuple_word": list(w)}
        self.Z.append(z)
        self._edges[key] = z
        self._keys.add(key)
        self._filled[i] += 1
        self.edge = len(self.Z)
        self.metrics["witnessed_transitions"] += 1
        self.metrics[kind + "_edges"] += 1
        return True

    def put(self, i, x, g, j, w, kind="membership"):
        require(
            0 <= i < len(self.R)
            and 0 <= j < len(self.R)
            and 0 <= x < self.a.d
            and 0 < abs(g) <= len(self.P.B),
            "Cover edge domain",
        )
        self._put(i, x, g, j, w, kind)
        # Inverse is exact for arbitrary K: R_j*a^-1=t(w^-1)R_i.
        self._put(j, x, -g, i, inv(w), "inverse_propagation")

    def merge(self, i, j, factors):
        require(0 <= j < i < len(self.R), "Coset merge ordering")
        c = self.proof(factors)
        old_edges = list(self.Z)
        pending = list(self._coincidences.items())
        if self._blocked_conflict is not None:
            a, b, w = self._blocked_conflict
            pending.append(((a, b), w))
            self._blocked_conflict = None

        def root(k):
            return j if k == i else k - (k > i)

        def p(k):
            return c if k == i else ()

        self.R = [r for k, r in enumerate(self.R) if k != i]
        self.Z = []
        self._edges = {}
        self._keys = set()
        self._filled = Counter()
        self._coincidences = OrderedDict()
        # If r_i=c r_j, outgoing collisions produce u^-1*c*v target
        # coincidences after this exact source/target rewriting.
        for z in old_edges:
            a, b = z["coset"], z["target"]
            w = self.proof(inv(p(a)) + tuple(z["tuple_word"]) + p(b))
            self.put(root(a), z["child"], z["letter"], root(b), w, "merge_transport")
        for (a, b), w in pending:
            self.coincidence(root(a), root(b), self.proof(inv(p(a)) + tuple(w) + p(b)))
        self.cursor = 0
        self._priority_cursor = 0
        self.merge_i, self.merge_j = 1, 0
        self._scan_iterator = None
        self._scan_signature = None
        self._attempts.clear()
        self.edge = len(self.Z)
        self.metrics["witnessed_coset_merges"] += 1

    def drain_coincidences(self, count):
        done = 0
        while self._coincidences and done < count:
            self.a.tick()
            (i, j), c = self._coincidences.popitem(last=False)
            self.merge(i, j, c)
            done += 1
        return done

    def merge_step(self, count):
        self.shared.refresh(check_target=not self._in_step)
        attempts = self.drain_coincidences(count)
        generation = (len(self.P.T), self.M.F.version, len(self.M.proofs))
        if generation != self.generation:
            self.generation = generation
            self.merge_i, self.merge_j = 1, 0
        while attempts < count and self.merge_i < len(self.R):
            self.a.tick()
            i, j = self.merge_i, self.merge_j
            self.merge_j += 1
            if self.merge_j >= self.merge_i:
                self.merge_i += 1
                self.merge_j = 0
            attempts += 1
            self.metrics["merge_pair_visits"] += 1
            if self.quotient.different(self.R[i], self.R[j]):
                continue
            target = multiply(self.R[i], inverse(self.R[j]))
            w = self.shared.lookup(target)
            if w is not None:
                self.coincidence(i, j, w)
                self.drain_coincidences(1)
            else:
                self.shared.request(target, ("merge", i, j), self.width)
        return attempts

    def _scans(self):
        for kind, letters, base, desired in constraints(self):
            starts = range(len(self.R)) if base is None else (0,)
            for row in starts:
                yield kind[0], row, letters, row if base is None else 0, desired

    def deduce(self, count):
        signature = (len(self.R), len(self.P.T), len(self.P.relations))
        if signature != self._scan_signature:
            self._scan_iterator = None
            self._scan_signature = signature
            self._scan_offset = 0
        if self._scan_iterator is None:
            self._scan_iterator = self._scans()
        done = 0
        while done < count:
            self.a.tick()
            try:
                kind, start, letters, end, desired = next(self._scan_iterator)
            except StopIteration:
                self._scan_iterator = self._scans()
                self._scan_offset = 0
                self.metrics["deduction_sweeps"] += 1
                break
            scan(self, start, letters, end, desired, kind)
            self._scan_offset += 1
            done += 1
            self.metrics["deduction_constraints_scanned"] += 1
            if self._coincidences:
                break
        return done

    def _key(self, index):
        i, off = divmod(index, self.width)
        x, li = divmod(off, len(self.letters))
        return i, x, self.letters[li]

    def schedule(self, max_rows):
        total = len(self.R) * self.width
        fair = self._schedule_turn % 4 == 3
        self._schedule_turn += 1
        if fair:
            for _ in range(total):
                if self.cursor >= total:
                    self.cursor = 0
                    self.rounds += 1
                    if (
                        self.clock() - self.last_growth
                        >= self.P.L["small_cover_growth_seconds"]
                    ):
                        self.goal = min(max_rows, max(self.goal + 1, self.goal * 2))
                        self.last_growth = self.clock()
                key = self._key(self.cursor)
                self.cursor += 1
                self.metrics["fair_base_probes"] += 1
                if key not in self._keys:
                    self.metrics["fair_base_gap_visits"] += 1
                    return key
        candidates = []
        for _ in range(min(total, 64)):
            key = self._key(self._priority_cursor % total)
            self._priority_cursor += 1
            self.metrics["benefit_schedule_probes"] += 1
            if key in self._keys:
                continue
            i, x, g = key
            missing = self.width - self._filled[i]
            # Reverse/rectangle neighbors make this gap useful to other rows.
            neighbors = sum(
                (i, y, h) in self._edges
                for y in range(self.a.d)
                for h in (g, -g)
                if y != x
            )
            self.metrics["benefit_neighbor_checks"] += 2 * (self.a.d - 1)
            candidates.append(((missing != 1, missing, -neighbors, key), key))
        if candidates:
            key = min(candidates)[1]
            self.metrics["preferred_one_gap_visits"] += (
                self.width - self._filled[key[0]] == 1
            )
            self.metrics["benefit_scheduled_gap_visits"] += 1
            return key
        # A sparse window is allowed to miss; the fair cursor still progresses.
        return None

    def attempt(self, key, max_rows):
        i, x, g = key
        v = list(self.R[i])
        v[x] = free(v[x] + (self.P.B[g - 1] if g > 0 else inv(self.P.B[-g - 1])))
        v = tuple(v)
        all_excluded = True
        for j, r in enumerate(self.R):
            self.a.tick()
            self.metrics["candidate_representative_visits"] += 1
            if self.quotient.different(v, r):
                self.metrics["membership_lookups_avoided_by_quotient"] += 1
                continue
            all_excluded = False
            t = multiply(v, inverse(r))
            w = self.shared.lookup(t)
            if w is not None:
                self.put(i, x, g, j, w)
                return
            self.shared.request(t, ("edge", i, x, g, j), self.width - self._filled[i])
        if (
            len(self._attempts) >= self.P.L["cache_entries"]
            and key not in self._attempts
        ):
            self._attempts.popitem(last=False)
        self._attempts[key] = self._attempts.get(key, 0) + 1
        if len(self.R) < min(self.goal, max_rows) and (
            all_excluded or (self._attempts[key] >= 2 and self.rounds >= 2)
        ):
            self.R.append(v)
            self.put(i, x, g, len(self.R) - 1, (), "provisional_split")
            self._scan_iterator = None
            self._scan_signature = None
            self.metrics["provisional_row_splits"] += 1
            # Immediate inverse and relation/coincidence consequences, no wait
            # for a fresh candidate or a change of K.
            self.deduce(2)
            self.drain_coincidences(1)
        else:
            self.metrics["deferred_unknown_edges"] += 1

    def step(self, count, storage_cap):
        self.shared.refresh()
        self._in_step = True
        try:
            return self._step(count, storage_cap)
        finally:
            self._in_step = False

    def _step(self, count, storage_cap):
        require(
            type(count) is int
            and count >= 0
            and type(storage_cap) is int
            and storage_cap >= 1,
            "Cover work/row caps",
        )
        require(
            self._scope == digest({"model": self.a.m, "B": self.P.B, "G": self.P.G}),
            "Cover action/basis target changed",
        )
        self.quotient.refresh()
        max_rows = min(storage_cap, self.P.L["small_cover_rows_max"])
        self.shared.work(max(1, count // 4), checked=True)
        self.merge_step(max(1, count // 8))
        for _ in range(count):
            self.a.tick()
            self.metrics["cover_work_turns"] += 1
            self.drain_coincidences(1)
            self.deduce(2)
            self.drain_coincidences(1)
            if (
                len(self.Z) == len(self.R) * self.width
                and not self._coincidences
                and self._blocked_conflict is None
            ):
                return {
                    "status": "CANDIDATE",
                    "representatives": self.R,
                    "transitions": self.Z,
                }
            key = self.schedule(max_rows)
            if key is not None:
                self.attempt(key, max_rows)
        return dict(self.summary(), status="UNKNOWN", reason="small_cover_quantum")

    def export(self):
        return {
            "schema": "small_cover_v1",
            "cover_search_version": 2,
            "goal": self.goal,
            "cursor": self.cursor,
            "rounds": self.rounds,
            "merge_i": self.merge_i,
            "merge_j": self.merge_j,
            "metrics": dict(self.metrics),
            "scope_sha256": self._scope,
            "schedule_turn": self._schedule_turn,
            "priority_cursor": self._priority_cursor,
            "shared": self.shared.export(),
            "pending_coincidences": [
                [i, j, list(c)] for (i, j), c in self._coincidences.items()
            ],
            "blocked_conflict": self._blocked_conflict,
            "gap_attempts": [[list(k), v] for k, v in self._attempts.items()],
            "deduction_cursor_resumed": False,
            "qualification": "Python finite-cover state only; caller must validate R/Z/image/membership first.",
        }

    def restore_validated(self, old, saved):
        require(saved["schema"] == "small_cover_v1", "Small-cover checkpoint schema")
        for k in ("goal", "cursor", "rounds", "merge_i", "merge_j"):
            require(type(saved[k]) is int and saved[k] >= 0, "Small-cover cursor")
            setattr(self, k, saved[k])
        require(
            1 <= self.goal <= self.P.L["small_cover_rows_max"]
            and len(old.R) <= self.goal,
            "Small-cover saved row budget",
        )
        self.R = [tuple(tuple(w) for w in t) for t in old.R]
        # The external restore has already validated these R/Z words. Reinsert
        # all edges so duplicate targets become coincidences instead of loss.
        self.Z = []
        self._edges = {}
        self._keys = set()
        self._filled = Counter()
        for z in old.Z:
            self.put(
                z["coset"],
                z["child"],
                z["letter"],
                z["target"],
                z["tuple_word"],
                "restore",
            )
        if saved.get("cover_search_version") == 2:
            require(
                saved["scope_sha256"] == self._scope,
                "Small-cover checkpoint action/basis",
            )
            self.shared.restore(saved["shared"])
            pending = list(saved["pending_coincidences"])
            if saved.get("blocked_conflict") is not None:
                pending.append(saved["blocked_conflict"])
            for i, j, c in pending:
                require(0 <= j < i < len(self.R), "Saved coincidence indices")
                word(
                    c,
                    len(self.P.T),
                    self.P.L["word_length"],
                    "Saved coincidence K word",
                )
                images = [[t["sections"][x] for t in self.P.T] for x in range(self.a.d)]
                actual = tuple(
                    expand(c, images[x], self.P.L["word_length"])
                    for x in range(self.a.d)
                )
                require(
                    self.a.tuple_equal(self.R[i], multiply(actual, self.R[j])),
                    "Saved coincidence false",
                )
                self.coincidence(i, j, c)
            for key in ("schedule_turn", "priority_cursor"):
                require(
                    type(saved[key]) is int and 0 <= saved[key] < 2**63,
                    "Small-cover saved scheduling counter",
                )
            self._schedule_turn = saved["schedule_turn"]
            self._priority_cursor = saved["priority_cursor"]
            attempts = saved.get("gap_attempts", [])
            require(
                type(attempts) is list and len(attempts) <= self.P.L["cache_entries"],
                "Saved gap attempt cap",
            )
            for key, n in attempts:
                require(
                    type(key) is list
                    and len(key) == 3
                    and all(type(v) is int for v in key),
                    "Saved gap key",
                )
                i, x, g = key
                require(
                    0 <= i < len(self.R)
                    and 0 <= x < self.a.d
                    and 0 < abs(g) <= len(self.P.B),
                    "Saved gap domain",
                )
                require(type(n) is int and 0 <= n < 2**63, "Saved gap attempt count")
                self._attempts[tuple(key)] = n
        require(
            type(saved["metrics"]) is dict
            and len(saved["metrics"]) <= 128
            and all(
                type(k) is str and type(v) is int and 0 <= v < 2**63
                for k, v in saved["metrics"].items()
            ),
            "Saved finite-cover metrics",
        )
        self.metrics.update(saved["metrics"])
        self.edge = len(self.Z)
