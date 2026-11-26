from .root_only import root_only, selected_depth_two

"""Common witnessed FULL-section image. No N-family selection or isolate filter.
K-products can contain arbitrarily many tuple generators up to explicit stage caps.
All membership hits are whole-tree checked; misses are inconclusive.
"""
from collections import deque, Counter
from .exact import require, word, free, inv, expand, Limit


def multiply(u, v):
    return tuple(free(a + b) for a, b in zip(u, v))


def inverse(u):
    return tuple(inv(w) for w in u)


def signed_words(rank, depth, count):
    letters = tuple(range(1, rank + 1)) + tuple(range(-rank, 0))
    done = 0
    # Depth first at each exact length: bounded streaming, no exponential BFS queue.
    for length in range(1, depth + 1):
        stack = [((), 0)]
        while stack:
            p, i = stack.pop()
            if len(p) == length:
                yield p
                done += 1
                if done >= count:
                    return
                continue
            for g in reversed(letters):
                if not p or p[-1] != -g:
                    stack.append((p + (g,), 0))


class TupleImage:
    def __init__(self, a, B, G, L):
        self.a = a
        self.B = tuple(tuple(w) for w in B)
        self.G = tuple(tuple(w) for w in G)
        self.L = L
        self.T = []
        self.parent_keys = set()
        self.section_keys = {}
        self.relations = []
        self.relkeys = set()
        self.metrics = Counter()
        self.version = 0

    def basis_word(self, w):
        return expand(w, self.G, self.L["word_length"])

    def add_relation(self, w, source):
        w = free(w)
        if not w or w in self.relkeys:
            return False
        if len(w) > self.L["relator_word_length"]:
            self.metrics["relator_word_length_hits"] += 1
            return False
        if len(self.relations) >= self.L["relator_cap"]:
            self.metrics["relator_cap_hits"] += 1
            return False
        if self.metrics["relator_total_letters"] + len(w) > self.L.get(
            "relator_total_letters", 2000000
        ):
            self.metrics["relator_total_letters_hits"] += 1
            return False
        raw = expand(w, self.B, self.L["word_length"])
        if not self.a.identity(raw):
            self.metrics["false_relation_candidates"] += 1
            return False
        self.relations.append(w)
        self.relkeys.add(w)
        self.metrics["verified_relations"] += 1
        self.metrics["relator_total_letters"] += len(w)
        return True

    def add_parent(self, p, source="generated", advertised=None):
        p = free(p)
        self.metrics["parents_considered"] += 1
        if p in self.parent_keys:
            return None
        root, sec = self.a.wreath(p)
        if root != tuple(range(self.a.d)):
            if advertised is not None:
                raise ValueError("Imported purported root-fixing parent moves root")
            self.metrics["parents_root_moving"] += 1
            return None
        if advertised is not None:
            require(
                len(advertised) == self.a.d and self.a.tuple_equal(sec, advertised),
                "Imported tuple mismatch",
            )
        self.parent_keys.add(p)
        if sec in self.section_keys:
            self.metrics["free_tuple_duplicates"] += 1
            return self.section_keys[sec]
        if len(self.T) >= self.L["tuple_cap"]:
            self.metrics["tuple_cap_hits"] += 1
            return None
        if all(self.a.identity(w) for w in sec):
            self.add_relation(self.basis_word(p), "identity_parent")
            self.metrics["identity_parents"] += 1
            return None
        j = len(self.T)
        self.T.append(
            {
                "parent_word": p,
                "sections": sec,
                "source": source,
                "dag": {"operation": "root_fixing_parent", "original_word": list(p)},
            }
        )
        self.section_keys[sec] = j
        self.version += 1
        self.metrics["tuple_generators_added"] += 1
        return j

    def import_saved(self, saved):
        P = saved["local_word_pool"]
        require(
            P["basis_words"] == [list(w) for w in self.B]
            and P["original_generator_words"] == [list(w) for w in self.G],
            "saved pool basis mismatch",
        )
        # Retain dense partials before isolated pairs: they are the purpose of this backend.
        for t in P.get("partial_tuples", [])[: self.L["saved_parent_cap"]]:
            p = word(t["parent_word"], self.a.q, self.L["word_length"])
            r, s = self.a.wreath(p)
            require(r == tuple(range(self.a.d)), "saved partial root mismatch")
            actual = [i for i, w in enumerate(s) if not self.a.identity(w)]
            require(actual == t["support"], "saved partial support mismatch")
            self.add_parent(p, "saved_full_tuple", s)
            self.metrics["saved_partial_verified"] += 1
        for t in P.get("isolated_pairs", [])[: self.L["saved_parent_cap"]]:
            x = t["child"]
            require(type(x) is int and 0 <= x < self.a.d, "saved child")
            s = [() for _ in range(self.a.d)]
            s[x] = word(t["target_word"], self.a.q, self.L["word_length"])
            self.add_parent(
                word(t["parent_word"], self.a.q, self.L["word_length"]),
                "saved_axis_tuple",
                s,
            )
            self.metrics["saved_isolated_verified"] += 1
        for w in P.get("identity_relators_basis", [])[: self.L["relator_cap"]]:
            self.add_relation(
                word(w, len(self.B), self.L["word_length"]), "saved_verified_relation"
            )

    def root_schreier_seeds(self):
        d = self.a.d
        ident = tuple(range(d))
        reps = [()]
        perms = [ident]
        seen = {ident: 0}
        todo = deque([0])
        letters = tuple(range(1, len(self.B) + 1)) + tuple(range(-len(self.B), 0))
        roots = {g: self.a.wreath(expand((g,), self.B))[0] for g in letters}
        emitted = 0
        for g in range(1, len(self.B) + 1):
            r = ident
            for n in range(1, self.L["root_power_cap"] + 1):
                self.a.tick()
                r = tuple(roots[g][r[x]] for x in range(d))
                if r == ident:
                    self.add_parent(expand((g,) * n, self.B), "root_order_power")
                    break
        while todo and emitted < self.L["root_seed_edges"]:
            i = todo.popleft()
            for g in letters:
                self.a.tick()
                r = tuple(roots[g][perms[i][x]] for x in range(d))
                if r not in seen and len(reps) < self.L["root_seed_states"]:
                    seen[r] = len(reps)
                    reps.append(reps[i] + (g,))
                    perms.append(r)
                    todo.append(seen[r])
                if r in seen:
                    w = free(reps[i] + (g,) + inv(reps[seen[r]]))
                    if w:
                        self.add_parent(
                            expand(w, self.B), "partial_root_schreier_closed_edge"
                        )
                        emitted += 1
                if emitted >= self.L["root_seed_edges"]:
                    break
        self.metrics["root_graph_states"] = len(reps)
        self.metrics["root_closed_edges"] = emitted

    def generate_short(self, depth, count):
        for w in signed_words(len(self.B), depth, count):
            self.a.tick()
            raw = expand(w, self.B, self.L["word_length"])
            root, sec = self.a.wreath(raw)
            self.metrics["short_basis_words"] += 1
            if root == tuple(range(self.a.d)):
                self.add_parent(raw, "short_full_tuple", sec)
                if all(self.a.identity(s) for s in sec):
                    self.add_relation(w, "short_whole_tree_identity")


class ProductFrontier:
    def __init__(self, image):
        self.P = image
        self.a = image.a
        self.L = image.L
        self.identity = tuple(() for _ in range(self.a.d))
        self.nodes = [(self.identity, ())]
        self.keys = {self.identity: 0}
        self.buckets = {}
        self.cursor = 0
        self.total_letters = 0
        self.metrics = Counter()
        self.version = 0
        self.add_bucket(self.identity, 0)
        self.next_letter = [0]
        self.letters = []
        self.known_generators = 0
        self.scan_node = 0

    def signature(self, t):
        # A deterministic finite filter only; every hit is independently exact checked.
        result = []
        for w in t:
            result.extend(selected_depth_two(self.a, w))
        return tuple(result)

    def add_bucket(self, t, i):
        self.buckets.setdefault(self.signature(t), []).append(i)

    def _schedule(self):
        # Rebuilt once on restore. Old shallow nodes remain valid, but cannot consume
        # the new depth reserves. Witness indices are never changed or evicted.
        if not hasattr(self, "depth_nodes"):
            self.depth_nodes = {}
            self.depth_positions = {}
            self.depth_cursor = 0
            self.bucket_cursor = {}
            self.lookup_hits = {}
            self.lookup_signatures = {}
            for i, (t, w) in enumerate(self.nodes):
                self.depth_nodes.setdefault(len(w), []).append(i)

    def grow(self, product_depth, attempts):
        self._schedule()
        for i in range(self.known_generators + 1, len(self.P.T) + 1):
            self.letters.extend((i, -i))
        self.known_generators = len(self.P.T)
        done = 0
        idle = 0
        polls = 0
        depths = list(range(min(product_depth, self.L.get("frontier_depth_bands", 8))))
        if not depths:
            return
        quota = max(
            1, self.L["frontier_cap"] // max(1, self.L.get("frontier_depth_bands", 8))
        )
        while polls < attempts:
            self.a.tick()
            polls += 1
            depth = depths[self.depth_cursor % len(depths)]
            self.depth_cursor += 1
            band = self.depth_nodes.get(depth, [])
            if not band:
                idle += 1
                continue
            off = self.depth_positions.get(depth, 0) % len(band)
            i = band[off]
            self.depth_positions[depth] = off + 1
            t, w = self.nodes[i]
            pos = self.next_letter[i]
            if pos >= len(self.letters):
                idle += 1
                continue
            # Admission BEFORE tuple construction. Retain the edge cursor until the
            # relevant quota grows; other depths still receive their quantum.
            if (
                len(self.depth_nodes.get(depth + 1, [])) >= quota
                or len(self.nodes) >= self.L["frontier_cap"]
            ):
                self.metrics["depth_admission_deferred"] += 1
                idle += 1
                continue
            g = self.letters[pos]
            if w and w[-1] == -g:
                self.next_letter[i] += 1
                done += 1
                continue
            sec = self.P.T[abs(g) - 1]["sections"]
            sec = sec if g > 0 else inverse(sec)
            v = multiply(t, sec)
            cost = sum(map(len, v))
            if (
                v not in self.keys
                and self.total_letters + cost > self.L["frontier_total_letters"]
            ):
                self.metrics["frontier_letter_deferred"] += 1
                idle += 1
                continue
            sig = None
            if v not in self.keys and all(len(z) <= self.L["word_length"] for z in v):
                sig = self.signature(v)
            self.next_letter[i] += 1
            done += 1
            self.metrics["product_attempts"] += 1
            idle = 0
            if v in self.keys:
                self.metrics["free_product_duplicates"] += 1
                continue
            if any(len(z) > self.L["word_length"] for z in v):
                self.metrics["product_word_cap"] += 1
                continue
            j = len(self.nodes)
            self.nodes.append((v, w + (g,)))
            self.next_letter.append(0)
            self.keys[v] = j
            self.total_letters += cost
            self.buckets.setdefault(sig, []).append(j)
            self.version += 1
            self.depth_nodes.setdefault(depth + 1, []).append(j)
            self.metrics["product_nodes"] += 1
            self.metrics["unique_product_nodes"] += 1
            self.metrics["max_tuple_factor_length"] = max(
                self.metrics["max_tuple_factor_length"], depth + 1
            )
        return done

    def lookup(self, t):
        self._schedule()
        self.metrics["membership_queries"] += 1
        if t in self.keys:
            return self.nodes[self.keys[t]][1]
        if t in self.lookup_hits:
            self.metrics["membership_success_cache_hits"] += 1
            return self.lookup_hits[t]
        if t not in self.lookup_signatures:
            if len(self.lookup_signatures) >= self.L["cache_entries"]:
                self.lookup_signatures.pop(next(iter(self.lookup_signatures)))
            self.lookup_signatures[t] = self.signature(t)
        bucket = self.buckets.get(self.lookup_signatures[t], [])
        pos = self.bucket_cursor.get(t, 0)
        checked = 0
        # Failed comparisons advance a per-target cursor. Appended bucket entries are
        # examined later; a task deadline keeps the currently interrupted comparison.
        while pos < len(bucket) and checked < self.L["membership_bucket_checks"]:
            self.a.tick()
            i = bucket[pos]
            self.metrics["membership_exact_checks"] += 1
            if self.a.tuple_equal(t, self.nodes[i][0]):
                self.metrics["membership_hits"] += 1
                if len(self.lookup_hits) >= self.L["cache_entries"]:
                    self.lookup_hits.pop(next(iter(self.lookup_hits)))
                self.lookup_hits[t] = self.nodes[i][1]
                return self.nodes[i][1]
            pos += 1
            checked += 1
            if (
                len(self.bucket_cursor) >= self.L["cache_entries"]
                and t not in self.bucket_cursor
            ):
                self.bucket_cursor.pop(next(iter(self.bucket_cursor)))
            self.bucket_cursor[t] = pos
            self.metrics["membership_unique_failed_checks"] += 1
        if pos < len(bucket):
            self.metrics["membership_bucket_caps"] += 1
        return None


def construct_cover(image, frontier, coset_cap):
    """Explicit constructive right-coset cover; no claim failed rows are distinct.
    Each membership witness is a product in the common full-tuple frontier.
    """
    a = image.a
    r = len(image.B)
    R = [tuple(() for _ in range(a.d))]
    Z = []
    row = 0
    letters = tuple(range(1, r + 1)) + tuple(range(-r, 0))
    while row < len(R):
        for x in range(a.d):
            for g in letters:
                a.tick()
                v = list(R[row])
                v[x] = free(v[x] + (image.B[g - 1] if g > 0 else inv(image.B[-g - 1])))
                v = tuple(v)
                hit = None
                for j, rep in enumerate(R):
                    w = frontier.lookup(multiply(v, inverse(rep)))
                    if w is not None:
                        hit = (j, w)
                        break
                if hit is None:
                    if len(R) >= coset_cap:
                        return {
                            "status": "UNKNOWN",
                            "reason": "constructive_coset_cap",
                            "rows": len(R),
                            "completed_transitions": len(Z),
                        }
                    R.append(v)
                    hit = (len(R) - 1, ())
                j, w = hit
                Z.append(
                    {
                        "coset": row,
                        "child": x,
                        "letter": g,
                        "target": j,
                        "tuple_word": list(w),
                    }
                )
        row += 1
    return {"status": "CANDIDATE", "representatives": R, "transitions": Z}
