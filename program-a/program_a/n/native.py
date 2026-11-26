"""Native GAP/FR interface over bound word families; no subprocess or admission here."""

from types import SimpleNamespace
from .. import native_gamma, index_backends
from ..contracts import need, digest, scoped
from ..executor import NativeReturn
from ..shared import felsch
from ..shared.weak_verify import expand, inv


def render_index(action, candidate, *, init_only=False):
    # Each mathematical alphabet has its own free group. Do not mix N proof symbols with original words.
    out = native_gamma.preamble() + native_gamma.original(action.packet["model"])
    out += (
        "OriginalFree:=FreeGroup(Q);; OriginalFamily:=FamilyObj(One(OriginalFree));;\n"
    )
    out += (
        "BasisFree:=FreeGroup("
        + str(len(candidate.certificate["basis_words"]))
        + ");;\n"
    )
    out += "NWords:=" + native_gamma.lit(candidate.certificate["N_generators"]) + ";;\n"
    out += "NWords:=List(NWords,w->AssocWordByLetterRep(OriginalFamily,w));;\n"
    out += "N:=SubgroupNC(G,List(NWords,w->PAWord(LetterRepAssocWord(w))));;\n"
    out += 'PAEvent("N_NATIVE_WORDS_READY");;\n'
    if init_only:
        return out + 'PAEvent("COMPLETE_PROTOCOL");;QuitGap(0);\n'
    return out + index_backends.native_index("G", "N")


def execute_index(action, candidate, runner, manifest, clock):
    need(runner is not None, "EXISTING_BOUND_NATIVE_RUNNER_REQUIRED")
    need(
        getattr(runner, "transport_kind", None)
        in ["BOUND_NATIVE", "FAKE_TRANSPORT_CONTROL"],
        "EXPLICIT_N_RUNNER_KIND",
    )
    a = runner.admit(manifest)
    need(
        a.get("status") == "PASS" and a.get("manifest_sha256") == digest(manifest),
        "N_NATIVE_ADMISSION",
    )
    request = {
        "manifest": manifest,
        "manifest_sha256": digest(manifest),
        "source": render_index(action, candidate),
        "raw_export": None,
        "native_checkpoint": False,
        "admission": a,
    }
    reply = runner.run_native(request)
    need(isinstance(reply, NativeReturn), "N_NATIVE_RETURN")
    out = index_backends.classify_native(
        reply.stdout,
        "Gamma",
        "N",
        returncode=reply.returncode,
        stderr=reply.stderr,
        resource_limit=reply.resource_reason,
        interrupted=reply.interrupted,
    )
    need(out.status.value != "Error", "N_NATIVE_FATAL:" + str(out.record()))
    # Native exactness remains the original N index, distinct from the normal-cover upper bound and I_n.
    if out.value is not None:
        need(
            out.value <= len(candidate.certificate["coset_cover"]["representatives"]),
            "N_INDEX_CONTRADICTS_VERIFIED_COVER",
        )
    record = out.record()
    if runner.transport_kind == "FAKE_TRANSPORT_CONTROL":
        record["evidence_level"] = "FAKE_TRANSPORT_CONTROL_NOT_NATIVE_EVIDENCE"
        record["scientific_certificate"] = False
    return record


def cover_presentation(B, G, N, relations):
    """Use the unchanged product renderer on N x Gamma in Gamma x Gamma.

    Projection onto factor0 maps its proof words to N words and proves a cover of
    Gamma by N. The second factor is entirely in the subgroup. This avoids changing
    the original renderer's degree>=2 contract or pretending tree arity is one.
    """
    r = len(B)
    shift = lambda w: [(1 if g > 0 else -1) * (r + abs(g)) for g in w]
    rel = [list(w) for w in relations] + [shift(w) for w in relations]
    rel += [[i, r + j, -i, -r - j] for i in range(1, r + 1) for j in range(1, r + 1)]
    return {
        "rank": r,
        "degree": 2,
        "relators": rel,
        "subgroup_generators": [list(expand(n, G)) for n in N]
        + [[r + i] for i in range(1, r + 1)],
    }


def gap_cover(a, B, G, N, L, C, runner, manifest, raw_export):
    need(runner is not None, "EXISTING_BOUND_NATIVE_RUNNER_REQUIRED")
    need(
        getattr(runner, "transport_kind", None)
        in ["BOUND_NATIVE", "FAKE_TRANSPORT_CONTROL"],
        "EXPLICIT_N_RUNNER_KIND",
    )
    need(raw_export is not None, "N_FELSCH_RAW_EXPORT_PATH")
    relations = manifest.get("verified_relators_basis", [])
    for w in relations:
        need(a.identity(expand(w, B)), "N_PRESENTATION_RELATOR_FALSE")
    data = cover_presentation(B, G, N, relations)
    request = {
        "manifest": manifest,
        "manifest_sha256": digest(manifest),
        "source": felsch.render(data, raw_export, L["coset_cap"]),
        "raw_export": str(raw_export),
        "native_checkpoint": False,
        "N_cover_transfer": "Gamma^2/(N x Gamma) -> Gamma/N by first projection",
    }
    admit = runner.admit(manifest)
    need(
        admit.get("status") == "PASS"
        and admit.get("manifest_sha256") == digest(manifest),
        "N_FELSCH_ADMISSION",
    )
    reply = runner.run_native(request)
    need(isinstance(reply, NativeReturn), "N_FELSCH_RETURN")
    if felsch.declared_workspace_limit(reply.stdout, reply.stderr, reply.returncode):
        from ..shared.weak_verify import Limit

        raise Limit("GAP_workspace")
    need(
        reply.returncode == 0
        and not reply.stderr
        and reply.stdout.count("DC_EXPORTED") == 1
        and reply.stdout.count("COMPLETE_PROTOCOL") == 1
        and reply.export is not None,
        "N_FELSCH_FATAL_OR_INCOMPLETE",
    )
    proxy = SimpleNamespace(
        B=B,
        T=[{"sections": [n, []]} for n in N] + [{"sections": [[], b]} for b in B],
        a=SimpleNamespace(d=2, tick=a.tick),
        L={
            **L,
            "secondary_cap": 100000,
            "word_length": L["export_word_length"],
            "frontier_total_letters": 10000000,
        },
    )
    reps, trans = felsch.decode(proxy, reply.export)
    C.transitions = {}
    C.edge_words = {}
    originals = [list(t[0]) for t in reps]
    for z in trans:
        if z["child"] != 0:
            continue
        # Primary symbols1..len(N) are first-factor N words. Other symbols live only
        # in the fully contained second factor and project to identity.
        projected = tuple(g for g in z["tuple_word"] if abs(g) <= len(N))
        C.transitions[z["coset"], z["letter"]] = z["target"]
        C.edge_words[z["coset"], z["letter"]] = projected

    def rewrite(w):
        i = 0
        out = ()
        for g in w:
            out += C.edge_words[i, g]
            i = C.transitions[i, g]
        if i:
            raise ValueError("N cover endpoint not identity")
        return out

    C.rewrite = rewrite
    normals = []
    letters = list(range(1, len(B) + 1)) + list(range(-len(B), 0))
    for i, n in enumerate(N, 1):
        for g in letters:
            try:
                nw = C.rewrite((-g,) + expand(n, G) + (g,))
            except ValueError:
                from ..shared.weak_verify import Limit

                raise Limit("N_FELSCH_FINITE_COVER_NORMALITY_UNPROVED")
            normals.append({"N_generator": i, "letter": g, "N_word": list(nw)})
    return {
        "schema_version": 1,
        "basis_words": B,
        "original_generator_words": G,
        "N_generators": N,
        "coset_cover": {
            "representatives": originals,
            "transitions": [
                {
                    "coset": i,
                    "letter": g,
                    "target": j,
                    "N_word": list(C.edge_words[i, g]),
                }
                for (i, g), j in C.transitions.items()
            ],
        },
        "normality": normals,
        "supported_lifts": [],
    }


def cover_relators(candidate, G):
    """Actual all-tree edge consequences of the already verified normal cover, in basis alphabet."""
    c = candidate.certificate
    B = c["basis_words"]
    N = c["N_generators"]
    T = c["coset_cover"]["representatives"]
    out = []
    for z in c["coset_cover"]["transitions"]:
        original = (
            tuple(T[z["coset"]])
            + expand((z["letter"],), B)
            + inv(tuple(T[z["target"]]))
            + inv(expand(z["N_word"], N))
        )
        out.append(list(expand(original, G)))
    return out
