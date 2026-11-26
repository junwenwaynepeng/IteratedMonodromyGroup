"""Independent raw signed-state word evaluator; right action, left factor first.
Only free cancellation. Whole-tree PASS requires a closed identity graph.
"""

import hashlib, json, time, math
from collections import deque

CONVENTION = "right_action_left_factor_first_input_indexed_sections_v1"


class Invalid(ValueError):
    pass


class Limit(RuntimeError):
    pass


def canonical(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(v):
    return hashlib.sha256(canonical(v).encode()).hexdigest()


def require(v, message):
    if not v:
        raise Invalid(message)


def integer(v, lo, hi, label):
    require(type(v) is int and lo <= v <= hi, label)
    return v


def inv(w):
    return tuple(-x for x in reversed(w))


def free(w):
    s = []
    for x in w:
        if s and s[-1] == -x:
            s.pop()
        else:
            s.append(x)
    return tuple(s)


def word(w, rank, cap=100000, label="word"):
    require(type(w) in (list, tuple) and len(w) <= cap, label + " shape/length")
    for g in w:
        require(type(g) is int and 0 < abs(g) <= rank, label + " alphabet")
    return tuple(w)


def expand(w, images, cap=100000):
    out = []
    for g in w:
        b = images[abs(g) - 1]
        b = b if g > 0 else inv(b)
        if len(out) + len(b) > cap:
            raise Limit("expanded_word_length")
        out.extend(b)
    return free(out)


def validate_model(packet, caps=None):
    require(__debug__, "Python optimization is unsupported; run without -O")
    require(type(packet) is dict, "packet object")
    caps = caps or {}
    m = packet.get("model", packet)
    require(
        type(m) is dict
        and type(m.get("roots")) is list
        and type(m.get("sections")) is list,
        "model roots/sections arrays",
    )
    roots = m["roots"]
    sections = m["sections"]
    q = len(roots)
    integer(q, 1, caps.get("model_states", 256), "model state count")
    require(type(roots[0]) is list, "root row")
    d = len(roots[0])
    integer(d, 2, caps.get("degree", 64), "degree")
    require(len(sections) == q, "section row count")
    if "names" in m:
        require(
            type(m["names"]) is list
            and len(m["names"]) == q
            and all(type(x) is str for x in m["names"])
            and len(set(m["names"])) == q,
            "state names",
        )
    for i, (r, s) in enumerate(zip(roots, sections)):
        require(
            type(r) is list
            and len(r) == d
            and all(type(x) is int for x in r)
            and sorted(r) == list(range(d)),
            "root permutation " + str(i),
        )
        require(type(s) is list and len(s) == d, "section dimensions " + str(i))
        for x in s:
            integer(x, -q, q, "section state code")
    return m, q, d


DEFAULT = {
    "seconds": 30.0,
    "identity_states": 20000,
    "identity_total_states": 2000000,
    "letter_steps": 100000000,
    "word_length": 100000,
    "cache_entries": 100000,
    "degree": 64,
    "model_states": 256,
}


def limits(values=None):
    z = dict(DEFAULT)
    for k, v in (values or {}).items():
        require(k in z, "unknown exact limit " + str(k))
        require(
            type(v) in (int, float) and math.isfinite(v) and v > 0,
            "positive exact limit " + k,
        )
        if k != "seconds":
            require(type(v) is int, "integer exact limit " + k)
        z[k] = v
    return z


class Action:
    def __init__(self, packet, values=None):
        self.L = limits(values)
        self.m, self.q, self.d = validate_model(packet, self.L)
        self.roots = self.m["roots"]
        self.sections = self.m["sections"]
        self.inverse_roots = [[r.index(x) for x in range(self.d)] for r in self.roots]
        self.deadline = time.monotonic() + self.L["seconds"]
        self.cache = {(): True}
        self.stats = {
            "identity_calls": 0,
            "identity_cache_hits": 0,
            "closed_identity_states": 0,
            "max_identity_graph": 0,
            "letter_steps": 0,
            "max_word_length": 0,
            "false_equalities": 0,
        }

    def tick(self):
        if time.monotonic() >= self.deadline:
            raise Limit("wallclock_seconds")

    def step(self, w, x):
        self.tick()
        out = []
        if len(w) > self.L["word_length"]:
            raise Limit("word_length")
        for n, g in enumerate(w):
            if n % 1024 == 0:
                self.tick()
            i = abs(g) - 1
            if g > 0:
                y = self.roots[i][x]
                s = self.sections[i][x]
            else:
                y = self.inverse_roots[i][x]
                s = -self.sections[i][y]
            if s:
                if out and out[-1] == -s:
                    out.pop()
                else:
                    out.append(s)
            x = y
        self.stats["letter_steps"] += len(w)
        if self.stats["letter_steps"] > self.L["letter_steps"]:
            raise Limit("letter_steps")
        return x, tuple(out)

    def wreath(self, w):
        root = []
        sec = []
        for x in range(self.d):
            y, s = self.step(w, x)
            root.append(y)
            sec.append(s)
        return tuple(root), tuple(sec)

    def identity(self, w):
        self.tick()
        w = free(w)
        self.stats["identity_calls"] += 1
        self.stats["max_word_length"] = max(self.stats["max_word_length"], len(w))
        if len(w) > self.L["word_length"]:
            raise Limit("word_length")
        if w in self.cache:
            self.stats["identity_cache_hits"] += 1
            return self.cache[w]
        todo = deque([w])
        seen = set()
        while todo:
            self.tick()
            u = todo.popleft()
            if u in seen or self.cache.get(u) is True:
                continue
            if self.cache.get(u) is False:
                self.cache[w] = False
                return False
            seen.add(u)
            if len(seen) > self.L["identity_states"]:
                raise Limit("identity_states")
            if (
                len(seen) + self.stats["closed_identity_states"]
                > self.L["identity_total_states"]
            ):
                raise Limit("identity_total_states")
            for x in range(self.d):
                y, s = self.step(u, x)
                if y != x:
                    self.stats["false_equalities"] += 1
                    if len(self.cache) < self.L["cache_entries"]:
                        self.cache[w] = False
                    return False
                if s and s not in seen:
                    todo.append(s)
        self.stats["closed_identity_states"] += len(seen)
        self.stats["max_identity_graph"] = max(
            self.stats["max_identity_graph"], len(seen)
        )
        for u in seen:
            if len(self.cache) < self.L["cache_entries"]:
                self.cache[u] = True
        return True

    def equal(self, u, v):
        return self.identity(free(tuple(u) + inv(v)))

    def tuple_equal(self, u, v):
        return all(self.equal(a, b) for a, b in zip(u, v))

    def fingerprint(self, w, depth=2):
        if depth == 0:
            return ()
        r, s = self.wreath(w)
        return r + tuple(self.fingerprint(v, depth - 1) for v in s)
