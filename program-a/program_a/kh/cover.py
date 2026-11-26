"""Turn verified input relations and root-fixing parents into a direct-image bound."""

import json
import subprocess
import tempfile
from pathlib import Path

from ..shared import checker, felsch
from ..shared.config import normalize
from ..shared.exact import Action, expand, require, word
from ..shared.tuples import TupleImage
from . import newtc, raw


def replay(packet, certificate):
    whole = checker.verify(packet, certificate)
    if whole["status"] != "PASS_DIRECT_IMAGE_BOUND":
        return whole
    # The independent interpreter requires an explicit identity tuple for an empty alphabet.
    replay_certificate = certificate
    if not certificate["tuple_generators"]:
        degree = len(packet["model"]["roots"][0])
        replay_certificate = dict(
            certificate,
            tuple_generators=[
                dict(parent_word=[], sections=[[] for _ in range(degree)])
            ],
        )
    independent = raw.verify(packet, replay_certificate)
    if independent["status"] != "PASS_DIRECT_IMAGE_BOUND":
        return independent
    bound = whole["all_level_I_upper_bound"]
    require(bound == independent["I_upper_bound"], "independent replay disagrees")
    return {
        "status": "CERTIFIED_DIRECT_IMAGE_BOUND",
        "all_level_I_upper_bound": bound,
        "whole_tree": whole,
        "raw_replay": independent,
    }


def solve(packet, pool, *, cosets=4096, seconds=60):
    action = Action(packet)
    limits = normalize({"coset_cap": cosets, "gap_coset_cap_max": cosets})
    original_basis = [[i] for i in range(1, action.q + 1)]
    basis = pool.get("basis_words", original_basis)
    reverse_basis = pool.get("original_generator_words", original_basis)
    require(basis and len(reverse_basis) == action.q, "missing basis expressions")
    for w in basis:
        word(w, action.q)
    for i, w in enumerate(reverse_basis, 1):
        require(
            action.equal(expand(word(w, len(basis)), basis), (i,)),
            "reverse basis mismatch",
        )
    image = TupleImage(action, basis, reverse_basis, limits)
    for w in pool["verified_relators_basis"]:
        relation = word(w, len(basis))
        require(action.identity(expand(relation, basis)), "invalid input relator")
        image.relations.append(relation)
    for row in pool["tuple_generators"]:
        parent = word(row["parent_word"], action.q)
        permutation, sections = action.wreath(parent)
        require(permutation == tuple(range(action.d)), "parent moves root")
        claimed = [word(w, action.q) for w in row["sections"]]
        require(
            len(claimed) == action.d and action.tuple_equal(sections, claimed),
            "incorrect sections",
        )
        image.T.append({"parent_word": parent, "sections": sections})

    with tempfile.TemporaryDirectory() as temp:
        export = Path(temp) / "cover.json"
        script = newtc.render(felsch.presentation(image), export, cosets)
        try:
            result = subprocess.run(
                ["gap", "-q", "-b", "-T"],
                input=script,
                text=True,
                capture_output=True,
                timeout=seconds,
            )
        except subprocess.TimeoutExpired:
            return {"status": "UNKNOWN", "reason": "GAP wall time"}
        lines = result.stdout.splitlines()
        if (
            result.returncode
            or result.stderr.strip()
            or "COMPLETE_PROTOCOL" not in lines
        ):
            raise RuntimeError(result.stderr or result.stdout[-1000:] or "GAP failed")
        if "DC_LIMIT COSETS" in lines:
            return {"status": "UNKNOWN", "reason": "coset limit"}
        require("DC_EXPORTED" in lines, "missing NEWTC export")
        representatives, transitions = felsch.decode(
            image, json.loads(export.read_text())
        )
    certificate = checker.package(
        packet, basis, reverse_basis, image.T, representatives, transitions
    )
    return dict(replay(packet, certificate), certificate=certificate)
