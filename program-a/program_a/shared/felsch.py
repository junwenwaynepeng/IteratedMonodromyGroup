"""Pure extraction of existing Felsch presentation/render/decode, no process runner."""

import json, re
from pathlib import Path
from .exact import require, word, expand, inv, free, Limit, CONVENTION, integer
from .proof_enumerator import render as _proof_render

PIN_GAP_VERSION = "4.12.1"
EXTRACTION_VERSION = "FULL_GAP_PROOF_CARRYING_FELSCH_V3_RESOURCE_STAGES"


def presentation(image):
    r = len(image.B)
    d = image.a.d
    rel = []
    for x in range(d):
        image.a.tick()
        for w in image.relations:
            rel.append([((1 if g > 0 else -1) * (x * r + abs(g))) for g in w])
    for x in range(d):
        for y in range(x + 1, d):
            for i in range(1, r + 1):
                for j in range(1, r + 1):
                    u = x * r + i
                    v = y * r + j
                    rel.append([u, v, -u, -v])
    sub = []
    for t in image.T:
        image.a.tick()
        w = []
        for x, s in enumerate(t["sections"]):
            b = image.basis_word(s)
            w.extend((1 if g > 0 else -1) * (x * r + abs(g)) for g in b)
        sub.append(w)
    if sum(map(len, rel)) + sum(map(len, sub)) > image.L.get(
        "presentation_total_letters", image.L["frontier_total_letters"]
    ):
        raise Limit("presentation_total_letters")
    return {"rank": r, "degree": d, "relators": rel, "subgroup_generators": sub}


def render(data, raw_path, coset_cap):
    script = _proof_render(data, raw_path, coset_cap)
    # Stage-only instrumentation. Weighted proof operations are unchanged.
    script = script.replace(
        "DCMain:=function()",
        'Print("DC_STAGE SCRIPT_LOADING\\n");\nDCMain:=function()',
        1,
    )
    script = script.replace(
        "debug:=", 'Print("DC_STAGE DATA_MATERIALIZED\\n");\ndebug:=', 1
    )
    script = script.replace(
        "Inv:=w->-Reversed(w);",
        'Print("DC_STAGE OCCURRENCES_BUILT\\n");\nInv:=w->-Reversed(w);',
        1,
    )
    script = script.replace(
        "DCMain();", 'Print("DC_STAGE SCRIPT_PARSED\\n");\nDCMain();', 1
    )
    return script


def workspace_failure_stage(stdout):
    if "DC_READY GAP=4.12.1" in stdout:
        return "native_after_readiness"
    if "DC_STAGE OCCURRENCES_BUILT" in stdout:
        return "proof_engine_initialization_before_readiness"
    if "DC_STAGE DATA_MATERIALIZED" in stdout:
        return "occurrence_index_initialization"
    if "DC_STAGE SCRIPT_PARSED" in stdout:
        return "data_materialization"
    if "DC_STAGE SCRIPT_LOADING" in stdout:
        return "script_parsing"
    return "native_before_readiness_unknown_substage"


def decode(image, z):
    from .newtc_decode import reduced_expand, checked_expression

    require(
        type(z) is dict
        and z.get("schema_version") == 1
        and z.get("gap_version") == PIN_GAP_VERSION,
        "GAP export version",
    )
    r = len(image.B)
    d = image.a.d
    require(
        z.get("rank") == r
        and z.get("degree") == d
        and z.get("primary_count") == len(image.T),
        "GAP export dimensions",
    )
    primary = len(image.T)
    defs = {i: (i,) for i in range(1, primary + 1)}
    total = primary
    require(
        type(z.get("secondary")) is list
        and len(z["secondary"]) <= image.L["secondary_cap"],
        "secondary list cap",
    )
    for pair in z["secondary"]:
        image.a.tick()
        require(type(pair) is list and len(pair) == 2, "secondary definition pair")
        i, w = pair
        require(
            type(i) is int and i == len(defs) + 1,
            "secondary definitions must be topological and contiguous",
        )
        v = word(w, i - 1, image.L["word_length"], "secondary expression")
        defs[i] = reduced_expand(
            v, [defs[k] for k in range(1, i)], image.L["word_length"], image.a.tick
        )
        total += len(defs[i])
        if total > image.L.get(
            "presentation_total_letters", image.L["frontier_total_letters"]
        ):
            raise Limit("decoded_secondary_total_letters")
    reps = []
    require(
        type(z.get("representatives")) is list
        and 1 <= len(z["representatives"]) <= image.L["coset_cap"],
        "export coset count",
    )
    for v in z["representatives"]:
        image.a.tick()
        v = word(v, r * d, image.L["word_length"], "ambient representative")
        t = [[] for _ in range(d)]
        for g in v:
            x = (abs(g) - 1) // r
            b = (abs(g) - 1) % r
            t[x].extend(image.B[b] if g > 0 else inv(image.B[b]))
        reps.append(tuple(free(w) for w in t))
    Z = []
    seen = set()
    require(
        type(z.get("transitions")) is list
        and len(z["transitions"]) == len(reps) * r * d * 2,
        "export transition count",
    )
    for v in z["transitions"]:
        image.a.tick()
        require(type(v) is list and len(v) == 5, "export transition shape")
        i, x, g, j, w = v
        require(
            all(type(a) is int for a in (i, x, g, j))
            and 0 <= i < len(reps)
            and 0 <= j < len(reps)
            and 0 <= x < d
            and 0 < abs(g) <= r,
            "export transition indices",
        )
        require((i, x, g) not in seen, "duplicate exported signed transition")
        seen.add((i, x, g))
        v = checked_expression(
            w, len(defs), image.L["presentation_total_letters"], image.a.tick
        )
        v = reduced_expand(
            v,
            [defs[k] for k in range(1, len(defs) + 1)],
            image.L["word_length"],
            image.a.tick,
        )
        total += len(v)
        if total > image.L.get(
            "presentation_total_letters", image.L["frontier_total_letters"]
        ):
            raise Limit("decoded_transition_total_letters")
        Z.append(
            {"coset": i, "child": x, "letter": g, "target": j, "tuple_word": list(v)}
        )
    return reps, Z


def decode_outcome(image, z, meta):
    """Every actual child retains metadata even when bounded decode stops."""
    try:
        R, Z = decode(image, z)
    except Limit as e:
        return {
            "status": "UNKNOWN",
            "reason": str(e),
            "stage": "decode",
            "process": meta,
        }
    except (ValueError, KeyError, IndexError, TypeError) as e:
        return {
            "status": "ERROR",
            "reason": "GAP_EXPORT_DECODE_ERROR:" + str(e),
            "stage": "decode",
            "process": meta,
        }
    return {
        "status": "CANDIDATE",
        "representatives": R,
        "transitions": Z,
        "process": meta,
    }


def declared_workspace_limit(stdout, stderr, returncode):
    """Only exact known GAP allocation panics may be typed before readiness.
    Signals, syntax errors, proof failures, foreign messages and unknown panics stay ERROR.
    """
    if type(returncode) is not int or returncode != 1:
        return False
    text = stdout + "\n" + stderr
    if any(
        v in text
        for v in (
            "Syntax error:",
            "Error,",
            "Error(",
            "FALSE",
            "DC_EXPORTED",
            "COMPLETE_PROTOCOL",
        )
    ):
        return False
    exact_panic = re.fullmatch(
        r"Panic in src/gasman\.c:[0-9]+: cannot extend the workspace any more!{2,4}",
        stderr.strip(),
    )
    known_line = r"(?:DC_STAGE (?:SCRIPT_LOADING|SCRIPT_PARSED|DATA_MATERIALIZED|OCCURRENCES_BUILT)|DC_FACTOR_PRODUCT_CONTROLS_PASS|DC_READY GAP=4\.12\.1|DC_COUNTS [0-9]+ [0-9]+ [0-9]+)"

    def known(line):
        if line.startswith("DC_TABLE_PROGRESS "):
            from .table_telemetry import decode_line

            try:
                decode_line(line)
                return True
            except ValueError:
                return False
        return re.fullmatch(known_line, line) is not None

    if exact_panic and all(known(line) for line in stdout.splitlines() if line.strip()):
        return True
    bare = (
        "cannot extend the workspace any more!!",
        "cannot extend the workspace any more!!!",
        "cannot extend the workspace any more!!!!",
    )
    return (
        "DC_READY GAP=4.12.1" in stdout
        and stderr.strip() in bare
        and all(known(line) for line in stdout.splitlines() if line.strip())
    )
