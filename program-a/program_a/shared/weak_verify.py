"""Sound finite word certificates. Right action, left factor first, input sections.
All words signed 1-based original-state codes unless schema explicitly says basis/N.
A resource limit returns UNKNOWN, never PASS. Standard library only.
"""

import time, json, argparse
from collections import deque


class Limit(Exception):
    pass


def inv(w):
    return tuple(-x for x in reversed(w))


def expand(w, generators):
    out = ()
    for x in w:
        if not isinstance(x, int) or not 1 <= abs(x) <= len(generators):
            raise ValueError("Invalid signed word code")
        v = tuple(generators[abs(x) - 1])
        out += v if x > 0 else inv(v)
    return out


class Action:
    def __init__(self, model, limits=None):
        self.model = model.get("model", model)
        self.roots = [tuple(p) for p in self.model["roots"]]
        self.sections = [tuple(s) for s in self.model["sections"]]
        self.q = len(self.roots)
        self.d = len(self.roots[0])
        self.limits = limits or {}
        self.deadline = time.monotonic() + self.limits.get("seconds", 60)
        self.cap = self.limits.get("identity_states", 10000)
        self.checks = 0
        self.max_seen = 0
        assert (
            self.q == len(self.sections)
            and all(sorted(p) == list(range(self.d)) for p in self.roots)
            and all(
                len(s) == self.d
                and all(isinstance(t, int) and abs(t) <= self.q for t in s)
                for s in self.sections
            )
        )
        self.signed = tuple(range(-self.q, self.q + 1))
        self.raw = {}
        for g in self.signed:
            if not g:
                self.raw[g] = (tuple(range(self.d)), (0,) * self.d)
            elif g > 0:
                self.raw[g] = (self.roots[g - 1], self.sections[g - 1])
            else:
                p = self.roots[-g - 1]
                s = self.sections[-g - 1]
                ip = tuple(p.index(x) for x in range(self.d))
                self.raw[g] = (ip, tuple(-s[ip[x]] for x in range(self.d)))
        cls = {g: 0 for g in self.signed}
        while True:
            signatures = {}
            new = {}
            for g in self.signed:
                p, s = self.raw[g]
                signature = (p, tuple(cls[x] for x in s))
                new[g] = signatures.setdefault(signature, len(signatures))
            if new == cls:
                break
            cls = new
        groups = {}
        for g, c in cls.items():
            groups.setdefault(c, []).append(g)
        reps = {c: min(v, key=lambda g: (abs(g), g < 0)) for c, v in groups.items()}
        self.alias = {g: reps[c] for g, c in cls.items()}
        self.cache = {}

    def tick(self):
        if time.monotonic() > self.deadline:
            raise Limit("wallclock_seconds")

    def reduce(self, w):
        out = []
        for g in w:
            if g not in self.alias:
                raise ValueError("Word outside original alphabet")
            g = self.alias[g]
            if not g:
                continue
            if out and self.alias[-g] == out[-1]:
                out.pop()
            else:
                out.append(g)
        return tuple(out)

    def step(self, w, x):
        sec = []
        y = x
        for g in w:
            p, s = self.raw[g]
            sec.append(s[y])
            y = p[y]
        return y, self.reduce(sec)

    def root(self, w):
        return tuple(self.step(w, x)[0] for x in range(self.d))

    def identity(self, w):
        w = self.reduce(w)
        if w in self.cache:
            return self.cache[w]
        queue = [w]
        seen = set()
        while queue:
            self.tick()
            v = queue.pop()
            if v in seen:
                continue
            if len(seen) >= self.cap:
                raise Limit("identity_states")
            seen.add(v)
            for x in range(self.d):
                y, u = self.step(v, x)
                if y != x:
                    self.cache[w] = False
                    return False
                if u not in seen:
                    queue.append(u)
        self.checks += 1
        self.max_seen = max(self.max_seen, len(seen))
        self.cache[w] = True
        return True

    def equal(self, u, v):
        return self.identity(inv(tuple(u)) + tuple(v))

    def fingerprint(self, w, depth=3):
        p = []
        for number in range(self.d**depth):
            x = number
            digits = []
            for _ in range(depth):
                digits.append(x % self.d)
                x //= self.d
            v = tuple(w)
            out = 0
            place = 1
            for x in digits:
                y, v = self.step(v, x)
                out += place * y
                place *= self.d
            p.append(out)
        return tuple(p)


def verify_certificate(model, cert, limits=None, _mode="complete"):
    """Replay every finite obligation; cover gives index UPPER bound only."""
    stage = "schema"
    try:
        if not __debug__:
            raise ValueError(
                "Certificate verification requires Python assertions enabled; do not use -O"
            )
        a = Action(model, limits)
        assert cert["schema_version"] == 1
        B = [tuple(w) for w in cert["basis_words"]]
        N = [tuple(w) for w in cert["N_generators"]]
        r = len(B)
        kN = len(N)
        assert r > 0 and all(isinstance(w, (list, tuple)) for w in N)
        original = cert["original_generator_words"]
        assert len(original) == a.q
        stage = "basis_generation"
        for g, w in enumerate(original, 1):
            assert a.equal(expand(w, B), (g,)), ("basis", g)
        cover = cert["coset_cover"]
        T = [tuple(w) for w in cover["representatives"]]
        assert T and a.identity(T[0])
        m = len(T)

        def indexed(rows, key, expected):
            ans = {}
            for z in rows:
                t = tuple(z[q] for q in key)
                assert t not in ans, "Duplicate obligation"
                ans[t] = z
            assert set(ans) == set(expected), "Missing/extra obligations"
            return ans

        letters = tuple(range(1, r + 1)) + tuple(range(-r, 0))
        stage = "coset_cover"
        edges = indexed(
            cover["transitions"],
            ("coset", "letter"),
            ((i, g) for i in range(m) for g in letters),
        )
        for (i, g), z in edges.items():
            j = z["target"]
            assert isinstance(j, int) and 0 <= j < m
            assert a.equal(T[i] + expand((g,), B), expand(z["N_word"], N) + T[j]), (
                "cover",
                i,
                g,
            )
        stage = "normality"
        normals = indexed(
            cert["normality"],
            ("N_generator", "letter"),
            ((i, g) for i in range(1, kN + 1) for g in letters),
        )
        for (i, g), z in normals.items():
            b = expand((g,), B)
            assert a.equal(inv(b) + N[i - 1] + b, expand(z["N_word"], N)), (
                "normal",
                i,
                g,
            )
        if _mode == "subgroup_only":
            return {
                "status": "PASS_SUBGROUP_DATA",
                "scope": "finite-index normal subgroup only; NO supported-insertion or all-level-I claim",
                "index_upper_bound": m,
                "whole_tree_checks": a.checks,
            }
        if _mode != "complete":
            raise ValueError("Unknown verifier mode")
        stage = "supported_lifts"
        lifts = indexed(
            cert["supported_lifts"],
            ("N_generator", "child"),
            ((i, x) for i in range(1, kN + 1) for x in range(a.d)),
        )
        for (i, x), z in lifts.items():
            p = expand(z["parent_N_word"], N)
            for y in range(a.d):
                out, sec = a.step(p, y)
                assert out == y and a.equal(sec, N[i - 1] if y == x else ()), (
                    "lift",
                    i,
                    x,
                    y,
                )
        return {
            "status": "PASS",
            "scope": "finite-index normal N with N^d inserted by parents IN N; original supplied action only",
            "index_upper_bound": m,
            "all_level_I_upper_bound": m**a.d,
            "exact_quotient_status": "NOT_ESTABLISHED_BY_THIS_CERTIFICATE",
            "basis_size": r,
            "N_generators": kN,
            "whole_tree_checks": a.checks,
            "max_identity_word_states": a.max_seen,
        }
    except Limit as e:
        return {"status": "UNKNOWN", "stage": stage, "reason": str(e)}
    except Exception as e:
        return {"status": "FAIL", "stage": stage, "reason": repr(e)}


def verify_subgroup_certificate(model, cert, limits=None):
    return verify_certificate(model, cert, limits, _mode="subgroup_only")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("certificate")
    p.add_argument("--seconds", type=float, default=60)
    p.add_argument("--output")
    args = p.parse_args()
    r = verify_certificate(
        json.load(open(args.input)),
        json.load(open(args.certificate)),
        {"seconds": args.seconds},
    )
    s = json.dumps(r, indent=2)
    print(s)
    if args.output:
        open(args.output, "w").write(s + "\n")
