"""N construction and proof-carrying normal covers, separate from insertion search."""

from dataclasses import dataclass
from ..contracts import need, digest
from ..shared.exact import word as checked_word
from ..shared.weak_verify import inv, expand, Limit
from .legacy.fast_covers import FastCover, FastClass2Cover, FastMixedClass2Cover
from .legacy.streaming import words


@dataclass
class Candidate:
    key: str
    family: str
    cover: object
    certificate: dict
    construction: dict


def specs(L, rank):
    out = list(L["families"])
    for m in L["universal_moduli"]:
        k = "universal_mod_" + str(m)
        if type(m) is int and m > 1 and m**rank <= L["coset_cap"] and k not in out:
            out.append(k)
    return out[: L["candidate_limit"]]


def formal(a, B, G, family, L):
    if family.startswith("class2_"):
        C = FastClass2Cover(a, B, int(family.split("_")[-1]), L["coset_cap"])
    elif family.startswith("mixed_class2_"):
        C = FastMixedClass2Cover(
            a, B, tuple(map(int, family[13:].split("_"))), L["coset_cap"]
        )
    else:
        allowed = family in [
            "root_sign_kernel",
            "root_kernel",
            "involution_derived",
        ] or family.startswith(("universal_mod_", "universal_mixed_"))
        need(allowed, "N_FAMILY_UNSUPPORTED:" + family)
        if family == "involution_derived":
            need(
                all(a.identity(b + b) for b in B), "INVOLUTION_COMMUTATOR_PRECONDITION"
            )
        C = FastCover(a, B, family, L["coset_cap"])
    cert = C.certificate(G)
    return Candidate(
        digest({"family": family, "basis": B, "N": C.N}),
        family,
        C,
        cert,
        {
            "kind": "FORMAL_FINITE_NORMAL_COVER",
            "index_is_upper_bound": True,
            "genuine_quotient_not_asserted": True,
            "normal_closure_interpretation": (
                "involution derived = normal closure of commutators only after all generator squares are proved identity"
                if family == "involution_derived"
                else "Proof-carrying cover, not inferred faithful quotient."
            ),
        },
    )


class ExpressionIndex:
    """Bounded original-word membership with N-word proofs; finite fingerprints only filter."""

    def __init__(self, a, N, L):
        self.a, self.N, self.L = a, N, L
        self.depth = min(3, L["fingerprint_depth"])
        while a.d**self.depth > 128:
            self.depth -= 1
        self.by = {}
        self.nodes = []
        for _, w in words(
            max(1, len(N)), L["membership_depth"], L["membership_nodes"], 0, False
        ):
            if not N and w:
                break
            raw = expand(w, N)
            f = a.fingerprint(raw, self.depth)
            if any(a.equal(raw, z[0]) for z in self.by.get(f, [])):
                continue
            self.by.setdefault(f, []).append((raw, w))
            self.nodes.append((raw, w))

    def find(self, target):
        if self.a.identity(target):
            return ()
        for raw, w in self.by.get(self.a.fingerprint(target, self.depth), []):
            if self.a.equal(raw, target):
                return w
        return None


class ExplicitCover:
    def __init__(self, a, B, N, L):
        self.a, self.B, self.N, self.L = a, B, N, L
        self.reps = [()]
        self.transitions = {}
        self.edge_words = {}
        self.membership = ExpressionIndex(a, N, L)

    def build(self, G):
        letters = list(range(1, len(self.B) + 1)) + list(range(-len(self.B), 0))
        i = 0
        while i < len(self.reps):
            t = expand(self.reps[i], self.B)
            for g in letters:
                self.a.tick()
                target = t + expand((g,), self.B)
                match = None
                for j, u in enumerate(self.reps):
                    nw = self.membership.find(target + inv(expand(u, self.B)))
                    if nw is not None:
                        match = (j, nw)
                        break
                if match is None:
                    if len(self.reps) >= self.L["coset_cap"]:
                        raise Limit(
                            "normal_closure_cover_capacity_or_membership_incomplete"
                        )
                    self.reps.append(self.reps[i] + (g,))
                    match = (len(self.reps) - 1, ())
                self.transitions[i, g], self.edge_words[i, g] = match
            i += 1
        normals = []
        for k, n in enumerate(self.N, 1):
            for g in letters:
                b = expand((g,), self.B)
                nw = self.membership.find(inv(b) + n + b)
                if nw is None:
                    raise Limit("normality_membership_incomplete")
                normals.append({"N_generator": k, "letter": g, "N_word": list(nw)})
        return {
            "schema_version": 1,
            "basis_words": self.B,
            "original_generator_words": G,
            "N_generators": self.N,
            "coset_cover": {
                "representatives": [expand(t, self.B) for t in self.reps],
                "transitions": [
                    {
                        "coset": i,
                        "letter": g,
                        "target": j,
                        "N_word": list(self.edge_words[i, g]),
                    }
                    for (i, g), j in self.transitions.items()
                ],
            },
            "normality": normals,
            "supported_lifts": [],
        }

    def rewrite(self, w):
        i = 0
        out = ()
        for g in w:
            out += tuple(self.edge_words[i, g])
            i = self.transitions[i, g]
        if i:
            raise ValueError("N membership not proved by this cover")
        return out


def normal_closure(a, B, G, seeds, L, cover_adapter=None):
    need(seeds and all(type(w) is list for w in seeds), "NORMAL_CLOSURE_SEED_WORDS")
    for w in seeds:
        checked_word(w, a.q, L["export_word_length"])
    N = []
    witnesses = []
    for _, t in words(
        len(B), L["normal_conjugator_depth"], L["normal_conjugator_count"], 0, False
    ):
        conj = expand(t, B)
        for si, seed in enumerate(seeds):
            raw = a.reduce(inv(conj) + tuple(seed) + conj)
            if a.identity(raw) or any(a.equal(raw, n) for n in N):
                continue
            if len(N) >= L["candidate_N_cap"]:
                raise Limit("candidate_N_cap")
            N.append(raw)
            witnesses.append({"seed_index": si, "conjugator": list(conj)})
    C = ExplicitCover(a, B, N, L)
    cert = C.build(G) if cover_adapter is None else cover_adapter(a, B, G, N, L, C)
    C.N = N
    return Candidate(
        digest({"normal_closure_seeds": seeds, "N": N, "basis": B}),
        "normal_closure",
        C,
        cert,
        {
            "kind": "BOUNDED_NORMAL_CONJUGATE_CLOSURE",
            "seeds": seeds,
            "generator_conjugate_witnesses": witnesses,
            "normal_closure_equality": "Only after unchanged finite normal-cover checker PASS: contains seeds and is normal; every generator is a seed conjugate.",
        },
    )


def normal_seed_specs(B, L):
    """Automatic bounded normal generators in the explicit discovered basis."""
    out = []
    if L["normal_closure_seeds"]:
        out.append(("configured_original_seed_words", L["normal_closure_seeds"]))
    if "commutators" in L["normal_closure_families"]:
        seeds = [
            list(inv(u) + inv(v) + tuple(u) + tuple(v))
            for i, u in enumerate(B)
            for v in B[i + 1 :]
        ]
        if not seeds:
            seeds = [list(tuple(B[0]) + inv(B[0]))]
        out.append(("automatic_basis_commutators", seeds))
    if "pair_differences" in L["normal_closure_families"]:
        for i, u in enumerate(B):
            for j, v in enumerate(B[i + 1 :], i + 1):
                out.append(
                    (
                        "automatic_basis_difference_" + str(i + 1) + "_" + str(j + 1),
                        [list(tuple(u) + inv(v))],
                    )
                )
    return out[: L["candidate_limit"]]
