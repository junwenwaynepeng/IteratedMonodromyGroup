"""Index and finite-cover adapters; never construct/replace a subgroup here."""

import re
from .contracts import Outcome, Status, need, evidence, digest, scoped
from .shared.felsch import render as felsch_render, decode_outcome
from .shared.small_cover import SmallCosetSearch, compact_certificate

NATIVE_PRODUCT_INDEX = """PAEvent("GAP_INDEX_ENTER");;
IDX:=Index(P,K);;
if IsInt(IDX) and IDX>=1 then Print("PA_INDEX FINITE_INDEX ",IDX,"\\n");
elif IDX=infinity then PAEvent("INFINITE_INDEX");
elif IDX=fail then PAEvent("INDEX_UNDECIDED");
else Error("UNEXPECTED_INDEX_RETURN");fi;;
PAEvent("COMPLETE_PROTOCOL");;QuitGap(0);
"""
BRANCH_PREDICATE = 'PAEvent("FR_IS_BRANCHED_INDEX_ENTER");;\nANSWER:=IsBranched(G);;\nif ANSWER=true then PAEvent("FR_IS_BRANCHED_TRUE");\nelif ANSWER=false then PAEvent("FR_IS_BRANCHED_FALSE");\nelse Error("UNEXPECTED_BRANCH_RESULT");fi;;\nPAEvent("COMPLETE_PROTOCOL");; QuitGap(0);\n'


def native_index(ambient="P", subgroup="K"):
    if (ambient, subgroup) == ("P", "K"):
        return NATIVE_PRODUCT_INDEX
    return NATIVE_PRODUCT_INDEX.replace(
        "Index(P,K)", "Index(" + ambient + "," + subgroup + ")"
    )


def classify_native(
    stdout,
    ambient,
    subgroup,
    *,
    returncode,
    stderr="",
    resource_limit=None,
    interrupted=False
):
    # Inspect the entire captured process outcome, not only success event lines.
    # An allocation limit may be classified by a separately pinned caller guard;
    # it may NEVER hide a conflicting complete result, syntax error or Error line.
    text = stdout + "\n" + stderr
    fatal = re.search(r"(?:Error[, (]|Syntax error|Segmentation fault|Traceback)", text)
    if "Panic" in text:
        known_workspace = re.fullmatch(
            r"Panic in src/gasman\.c:[0-9]+: cannot extend the workspace any more!{2,4}",
            stderr.strip(),
        )
        fatal = fatal or not (resource_limit and known_workspace)
    if (
        fatal
        or (returncode not in (0, 1) and not interrupted)
        or (returncode != 0 and not resource_limit and not interrupted)
    ):
        return Outcome(
            Status.Error,
            ambient,
            subgroup,
            "NATIVE_PROCESS_ERROR",
            "NATIVE_OUTPUT",
            reason="Nonzero/signal/fatal GAP output; no success promotion.",
            evidence=(
                {
                    "returncode": returncode,
                    "stderr": stderr,
                    "raw_events": [
                        l[9:] for l in stdout.splitlines() if l.startswith("PA_INDEX ")
                    ][:64],
                },
            ),
        )
    if resource_limit:
        if "COMPLETE_PROTOCOL" in stdout:
            return Outcome(
                Status.Error,
                ambient,
                subgroup,
                "CONFLICTING_RESOURCE_AND_SUCCESS",
                "NATIVE_OUTPUT",
            )
        return Outcome(
            Status.ResourceLimit,
            ambient,
            subgroup,
            "RESOURCE_LIMIT",
            "NATIVE_OUTPUT",
            reason=resource_limit,
        )
    if interrupted:
        return Outcome(
            Status.Unknown,
            ambient,
            subgroup,
            "INTERRUPTED",
            "NATIVE_OUTPUT",
            reason="Interrupted is not a completed search.",
        )
    if stderr.strip():
        return Outcome(
            Status.Error,
            ambient,
            subgroup,
            "UNCLASSIFIED_NATIVE_STDERR",
            "NATIVE_OUTPUT",
            reason=stderr,
        )
    events = [
        l[len("PA_INDEX ") :] for l in stdout.splitlines() if l.startswith("PA_INDEX ")
    ]
    need(
        events.count("MODEL_READY") == 1
        and events.count("COMPLETE_PROTOCOL") == 1
        and events[-1] == "COMPLETE_PROTOCOL",
        "NATIVE_INCOMPLETE_OR_DUPLICATE_PROTOCOL",
    )
    answers = [
        e
        for e in events
        if e.startswith("FINITE_INDEX ")
        or e
        in (
            "INFINITE_INDEX",
            "INDEX_UNDECIDED",
            "FR_IS_BRANCHED_TRUE",
            "FR_IS_BRANCHED_FALSE",
        )
    ]
    need(len(answers) == 1, "NATIVE_CONFLICTING_OR_MISSING_OUTCOME")
    raw = answers[0]
    if raw.startswith("FINITE_INDEX "):
        need(re.fullmatch(r"FINITE_INDEX [1-9][0-9]*", raw), "NATIVE_INDEX_VALUE")
        return Outcome(
            Status.ExactIndex,
            ambient,
            subgroup,
            raw,
            "NATIVE_RETURN",
            int(raw.split()[1]),
        )
    if raw == "FR_IS_BRANCHED_TRUE":
        return Outcome(
            Status.Candidate,
            ambient,
            subgroup,
            raw,
            "NATIVE_RETURN",
            reason="FR property alone is not an independent I_n certificate.",
        )
    return Outcome(
        Status.Unknown,
        ambient,
        subgroup,
        raw,
        "NATIVE_RETURN",
        reason="No finite bound obtained; no negative I_n conclusion.",
    )


def transfer_to_image(outcome, action, subgroup, receipt_refs=None):
    """Explicit proof obligations; exact source index is retained separately."""
    if outcome.status not in (Status.ExactIndex, Status.FiniteUpperBound):
        return outcome
    need(
        outcome.identity_sha256 == digest(action.identity.record())
        and outcome.subgroup_sha256 == digest(subgroup.statement),
        "RESULT_SOURCE_IDENTITY_MISMATCH",
    )
    need(
        outcome.ambient == subgroup.ambient and outcome.subgroup == subgroup.backend,
        "RESULT_ACTUAL_AMBIENT_AND_SUBGROUP",
    )
    refs = receipt_refs or {}
    used = list(subgroup.receipts)
    if subgroup.backend in ("N", "L"):
        need("supported_inclusion" in refs, "NEED_N_OR_L_POWER_CONTAINED_IN_H")
        used.append(
            evidence(
                refs["supported_inclusion"],
                action.identity,
                "SUBGROUP_POWER_CONTAINED_IN_H",
                subgroup.statement,
            )
        )
        value = outcome.value**action.identity.degree
    else:
        value = outcome.value
        if subgroup.backend == "K_GAP":
            need("contained_in_H" in refs, "NEED_K_CONTAINED_IN_H")
            used.append(
                evidence(
                    refs["contained_in_H"],
                    action.identity,
                    "K_CONTAINED_IN_H",
                    subgroup.statement,
                )
            )
    # Exactness transfers to H only if equality is supported; never to I_n.
    exact_H = subgroup.backend == "H" or "equals_H" in refs
    if subgroup.backend == "K_GAP" and "equals_H" in refs:
        used.append(
            evidence(
                refs["equals_H"], action.identity, "K_EQUALS_H", subgroup.statement
            )
        )
    status = (
        Status.ExactIndex
        if (
            subgroup.backend in ("H", "K_GAP")
            and exact_H
            and outcome.status == Status.ExactIndex
        )
        else Status.FiniteUpperBound
    )
    return scoped(
        Outcome(
            status,
            "Gamma^d",
            "H",
            outcome.raw_status,
            "DERIVED_FROM_NATIVE_WITH_PINNED_OBLIGATIONS",
            value,
            "Index of H only; no exact finite-level I_n assertion.",
            tuple(used),
        ),
        action,
        {"ambient": "Gamma^d", "target": "psi(St_Gamma(1))"},
    )


def presented_to_image(outcome, ambient, action, subgroup, receipts=None):
    need(
        outcome.ambient == ambient and outcome.subgroup == "PresentedSubgroup",
        "PRESENTATION_AMBIENT_MISMATCH",
    )
    if outcome.status not in (Status.ExactIndex, Status.FiniteUpperBound):
        return outcome
    need(
        outcome.identity_sha256 == digest(action.identity.record())
        and outcome.subgroup_sha256 == digest(subgroup.statement),
        "PRESENTED_RESULT_SOURCE_MISMATCH",
    )
    # A surjection can collapse distinct presented cosets. Exactness is lost.
    product_bound = scoped(
        Outcome(
            Status.FiniteUpperBound,
            "Gamma^d",
            subgroup.backend,
            outcome.raw_status,
            "PRESENTATION_SURJECTION",
            outcome.value,
            "Partial verified relators do not identify the actual action group.",
        ),
        action,
        subgroup.statement,
    )
    return transfer_to_image(product_bound, action, subgroup, receipts)


def small_cover(image, membership, **kwargs):
    return SmallCosetSearch(image, membership, **kwargs)
