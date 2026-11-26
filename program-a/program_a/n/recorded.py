"""Reuse a bound normal-cover proof without repeating candidate/quotient enumeration.
The unchanged subgroup checker still validates every restored finite obligation.
"""

import copy
from ..contracts import need, digest
from ..shared.exact import word
from ..shared.weak_verify import expand
from .candidates import Candidate


class RecordedCover:
    def __init__(self, certificate, Nbasis=None):
        self.N = certificate["N_generators"]
        self.B = certificate["basis_words"]
        self.reps = certificate["coset_cover"]["representatives"]
        self.Nbasis = Nbasis
        self.edges = {
            (z["coset"], z["letter"]): (z["target"], tuple(z["N_word"]))
            for z in certificate["coset_cover"]["transitions"]
        }

    def rewrite(self, w):
        i = 0
        out = ()
        for g in w:
            i, nw = self.edges[i, g]
            out += nw
        if i:
            raise ValueError("Recorded cover gives no N membership proof")
        return out


def definition(candidate):
    return {
        "candidate_key": candidate.key,
        "family": candidate.family,
        "certificate": copy.deepcopy(candidate.certificate),
        "construction": copy.deepcopy(candidate.construction),
        "N_basis_words": copy.deepcopy(getattr(candidate.cover, "Nbasis", None)),
    }


def restore(a, B, G, data, L):
    cert = copy.deepcopy(data["certificate"])
    need(
        digest(cert["basis_words"]) == digest(B)
        and digest(cert["original_generator_words"]) == digest(G),
        "RESTORED_N_COVER_BASIS_CHANGED",
    )
    for n in cert["N_generators"]:
        word(n, a.q, L["export_word_length"])
    if data["family"] == "normal_closure":
        key = digest(
            {
                "normal_closure_seeds": data["construction"]["seeds"],
                "N": cert["N_generators"],
                "basis": B,
            }
        )
    else:
        key = digest({"family": data["family"], "basis": B, "N": cert["N_generators"]})
    need(key == data["candidate_key"], "RESTORED_N_CANDIDATE_ALPHABET_CHANGED")
    C = RecordedCover(cert, data.get("N_basis_words"))
    if C.Nbasis is not None:
        need(len(C.Nbasis) == len(C.N), "RESTORED_N_BASIS_EXPRESSIONS")
        for n, b in zip(C.N, C.Nbasis):
            need(a.equal(n, expand(b, B)), "RESTORED_N_BASIS_PROOF_FALSE")
    return Candidate(key, data["family"], C, cert, data["construction"])
