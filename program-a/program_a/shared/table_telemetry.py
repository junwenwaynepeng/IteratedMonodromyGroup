"""Strict diagnostic transport. Counts never replace either scientific checker."""

import json, re, copy

MAX_INT = 2**53 - 1
PHASES = {
    "initialization",
    "definition",
    "merge",
    "drain",
    "scan",
    "complete",
    "limited",
}
REQUIRED = {
    "stage",
    "schema_version",
    "current_representatives",
    "ambient_positive_generators",
    "signed_columns",
    "established_transitions",
    "unfilled_transitions",
    "total_transition_slots",
    "phase",
    "native_cpu_ms",
    "native_elapsed_ms",
    "table_complete",
    "evidence",
    "subgroup_label",
    "native_attempt_id",
    "sample_sequence",
    "snapshot_status",
}
OPTIONAL = {"table_snapshot", "subgroup_epoch", "telemetry_status"}


def need(ok, label):
    if not ok:
        raise ValueError("INVALID_FELSCH_TABLE_PROGRESS:" + label)


def integer(v, lo=0, hi=MAX_INT):
    return type(v) is int and lo <= v <= hi


def validate_progress(z, *, allow_retained=False):
    allowed = REQUIRED | OPTIONAL | ({"last_table_sample"} if allow_retained else set())
    need(type(z) is dict and REQUIRED <= z.keys() and z.keys() <= allowed, "fields")
    need(
        z["stage"] in ("FELSCH_TABLE_PROGRESS", "NEWTC_TABLE_PROGRESS")
        and type(z["schema_version"]) is int
        and z["schema_version"] == 1,
        "version",
    )
    m = z["ambient_positive_generators"]
    n = z["current_representatives"]
    C = z["signed_columns"]
    E = z["established_transitions"]
    U = z["unfilled_transitions"]
    T = z["total_transition_slots"]
    need(
        integer(m, 1, 4096) and integer(n, 1) and integer(C, 2, 8192) and C == 2 * m,
        "dimensions",
    )
    need(
        all(integer(x) for x in [E, U, T]) and E + U == T == n * C,
        "signed_slot_invariant",
    )
    need(
        type(z["phase"]) is str
        and z["phase"] in PHASES
        and integer(z["native_cpu_ms"])
        and integer(z["native_elapsed_ms"]),
        "phase_clock",
    )
    need(
        type(z["table_complete"]) is bool
        and (not z["table_complete"] or (z["phase"] == "complete" and U == 0)),
        "complete",
    )
    need(
        z["evidence"] == "NATIVE_PARTIAL_DIAGNOSTIC"
        and z["subgroup_label"] in ("K", "H"),
        "scope",
    )
    need(
        type(z["native_attempt_id"]) is str
        and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", z["native_attempt_id"]) is not None,
        "attempt",
    )
    need(
        integer(z["sample_sequence"], 1)
        and z["snapshot_status"]
        in ("NOT_DUE", "CELLS", "BINS", "BUDGET_EXHAUSTED", "SUPPRESSED"),
        "sequence_snapshot_status",
    )
    if "telemetry_status" in z:
        need(z["telemetry_status"] == "BYTE_BUDGET_EXHAUSTED", "telemetry_status")
    if "subgroup_epoch" in z:
        need(
            type(z["subgroup_epoch"]) is str
            and re.fullmatch("[0-9a-f]{64}", z["subgroup_epoch"]) is not None,
            "epoch",
        )
    if "table_snapshot" in z:
        validate_snapshot(z["table_snapshot"], z)
    if "last_table_sample" in z:
        old = z["last_table_sample"]
        validate_progress(old)
        need(
            "table_snapshot" not in z and "table_snapshot" in old,
            "retained_snapshot_shape",
        )
        for key in ("native_attempt_id", "subgroup_label", "subgroup_epoch"):
            need(old.get(key) == z.get(key), "retained_context_" + key)
        need(
            old["sample_sequence"] < z["sample_sequence"]
            and old["native_elapsed_ms"] <= z["native_elapsed_ms"]
            and old["native_cpu_ms"] <= z["native_cpu_ms"],
            "retained_sample_clock",
        )
    need(len(json.dumps(z, separators=(",", ":"))) <= 32768, "serialized_cap")
    return z


def validate_snapshot(s, z):
    need(type(s) is dict, "snapshot_object")
    base = {
        "schema_version",
        "subgroup_label",
        "native_attempt_id",
        "sample_sequence",
        "mode",
    }
    need(
        base <= s.keys() and s.keys() <= base | {"cells", "bins", "subgroup_epoch"},
        "snapshot_fields",
    )
    for k in (
        "schema_version",
        "subgroup_label",
        "native_attempt_id",
        "sample_sequence",
    ):
        need(type(s[k]) is type(z[k]) and s[k] == z[k], "snapshot_context_" + k)
    if "subgroup_epoch" in z:
        need(s.get("subgroup_epoch") == z["subgroup_epoch"], "snapshot_epoch")
    n = z["current_representatives"]
    C = z["signed_columns"]
    m = z["ambient_positive_generators"]
    areas = 0
    E = 0
    U = 0
    if s["mode"] == "cells":
        need(
            "bins" not in s and type(s.get("cells")) is list and len(s["cells"]) <= 256,
            "cell_cap",
        )
        seen = set()
        sources = {}
        ids = {}
        for c in s["cells"]:
            need(type(c) is list and len(c) == 5, "cell_shape")
            row, source, col, g, target = c
            need(
                integer(row, 0, n - 1)
                and integer(source, 1)
                and integer(col, 0, C - 1)
                and type(g) is int
                and g == (col + 1 if col < m else -(col - m + 1)),
                "cell_coordinate",
            )
            need(
                (row, col) not in seen
                and sources.get(row, source) == source
                and ids.get(source, row) == row,
                "duplicate_or_conflicting_cell",
            )
            seen.add((row, col))
            sources[row] = source
            ids[source] = row
            need(target is None or integer(target, 1), "target")
            areas += 1
            E += target is not None
            U += target is None
    else:
        need(
            s["mode"] == "bins"
            and "cells" not in s
            and type(s.get("bins")) is list
            and len(s["bins"]) <= 256,
            "bin_cap",
        )
        seen = []
        for b in s["bins"]:
            need(
                type(b) is dict
                and set(b)
                == {
                    "row_start",
                    "row_end",
                    "col_start",
                    "col_end",
                    "established",
                    "unfilled",
                },
                "bin_shape",
            )
            a, h, c, k, e, u = (
                b[x]
                for x in [
                    "row_start",
                    "row_end",
                    "col_start",
                    "col_end",
                    "established",
                    "unfilled",
                ]
            )
            need(
                integer(a, 0, n - 1)
                and integer(h, a + 1, n)
                and integer(c, 0, C - 1)
                and integer(k, c + 1, C)
                and integer(e)
                and integer(u)
                and e + u == (h - a) * (k - c),
                "bin_area",
            )
            need(
                all(
                    h <= aa or hh <= a or k <= cc or kk <= c for aa, hh, cc, kk in seen
                ),
                "overlapping_bins",
            )
            seen.append((a, h, c, k))
            areas += (h - a) * (k - c)
            E += e
            U += u
    need(
        E <= z["established_transitions"] and U <= z["unfilled_transitions"],
        "snapshot_exceeds_exact_counts",
    )
    if areas == z["total_transition_slots"]:
        need(
            E == z["established_transitions"] and U == z["unfilled_transitions"],
            "full_snapshot_totals",
        )
    return s


def decode_line(line):
    need(line.startswith("DC_TABLE_PROGRESS "), "prefix")
    try:
        z = json.loads(line[18:])
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError("INVALID_FELSCH_TABLE_PROGRESS:json") from e
    return validate_progress(z)


def carry_table_sample(current, previous):
    """Carry one original frame; never relabel its rows/counts as current."""
    validate_progress(current)
    if "table_snapshot" in current or previous is None:
        return current
    validate_progress(previous)
    z = dict(current, last_table_sample=copy.deepcopy(previous))
    return validate_progress(z, allow_retained=True)


def table_progress_for_events(events):
    current = next(
        (
            e
            for e in reversed(events)
            if e.get("stage") in ("FELSCH_TABLE_PROGRESS", "NEWTC_TABLE_PROGRESS")
        ),
        None,
    )
    if current is None:
        return None
    if "table_snapshot" in current:
        return current
    previous = next(
        (
            e
            for e in reversed(events)
            if e.get("stage") in ("FELSCH_TABLE_PROGRESS", "NEWTC_TABLE_PROGRESS")
            and "table_snapshot" in e
        ),
        None,
    )
    return carry_table_sample(current, previous)


def latest_native_stage(events):
    """Current counters plus a bounded original sample survive late HTTP polls."""
    if not events:
        return None
    current = events[-1]
    if any(e.get("stage") == "NEWTC_TABLE_PROGRESS" for e in events):
        return table_progress_for_events(events)
    if current.get("stage", "").startswith("DC_COUNTS "):
        return table_progress_for_events(events) or current
    if current.get("stage") in ("FELSCH_TABLE_PROGRESS", "NEWTC_TABLE_PROGRESS"):
        return table_progress_for_events(events)
    return current
