"""Explicit N end-to-end session. Caller owns admission, resource lifecycle and persistence."""

import json, time, copy
from ..contracts import need, digest, identify
from ..shared.exact import Limit as ExportLimit
from ..shared.weak_verify import Limit, verify_subgroup_certificate, expand, inv
from .config import normalize, structural
from .basis import obtain
from .candidates import formal, specs, normal_closure, normal_seed_specs
from .legacy.search_action import SearchAction
from .legacy.streaming import words
from .pool import InsertionPool
from .assembly import assemble, check_and_raw
from .timing import Clocks
from .seeds import root_seeds
from . import native
from .strong import StrongSearch
from . import recorded
from .optimizations import CompletionSharing


def run(
    action,
    limits=None,
    *,
    basis_hint=None,
    checkpoint=None,
    runner=None,
    raw_export=None,
    checkpoint_writer=None,
    progress=None,
    retained_parents=None
):
    action.identity.require_match(identify(action.packet).record())
    L = normalize(limits)
    clock = Clocks()
    end = clock.started + L["seconds"]
    remaining = lambda: max(0.0, end - time.monotonic())
    result = {
        "schema": "N_method_result_v1",
        "identity": action.identity.record(),
        "action_source": action.source,
        "status": "UNKNOWN",
        "candidates": [],
        "certificates": [],
        "limits": L,
        "checkpoint": None,
        "discovery_mode": (
            "CONTINUATION_OF_BOUND_CHECKPOINT"
            if checkpoint
            else (
                "SUPPLIED_BASIS_NOT_FROM_ZERO"
                if basis_hint
                else "FROM_INPUT_NO_WARM_WITNESSES"
            )
        ),
        "scientific_scope": "Exact bound action only; finite normal-cover bounds, not exact quotient or I_n classification.",
        "native_calls": 0,
        "timing": None,
    }
    completion_sharing = CompletionSharing()
    restore_complete = checkpoint is None
    a = P = B = G = None
    constructed = []
    cursor = 0
    processed = 0
    seed_cursor = 0
    seed_complete = False
    found = {}
    strong_searches = {}
    history = []
    prior_certified = set((checkpoint or {}).get("accepted_certificate_sha256", []))
    if basis_hint:
        action.identity.require_match(basis_hint.get("identity"))
    if checkpoint:
        need(
            checkpoint.get("schema") == "N_method_checkpoint_v1", "N_CHECKPOINT_SCHEMA"
        )
        action.identity.require_match(checkpoint.get("identity"))
        need(
            checkpoint.get("action_source") == action.source,
            "N_CHECKPOINT_SOURCE_CHANGED",
        )
        need(
            checkpoint["strategy_sha256"] == structural(L),
            "N_CHECKPOINT_STRATEGY_CHANGED",
        )
        need(
            checkpoint["payload_sha256"]
            == digest({k: v for k, v in checkpoint.items() if k != "payload_sha256"}),
            "N_CHECKPOINT_PAYLOAD_CHANGED",
        )
        basis_hint = {
            "identity": checkpoint["identity"],
            "basis_words": checkpoint["basis_words"],
            "original_generator_words": checkpoint["original_generator_words"],
        }

    def snapshot():
        if P is None:
            return
        z = {
            "schema": "N_method_checkpoint_v1",
            "identity": action.identity.record(),
            "action_source": action.source,
            "strategy_sha256": structural(L),
            "basis_words": [list(w) for w in B],
            "original_generator_words": [list(w) for w in G],
            "pool": P.checkpoint(),
            "word_cursor": cursor,
            "stream_words_processed": processed,
            "root_seed_cursor": seed_cursor,
            "root_seeds_complete": seed_complete,
            "candidate_definitions": [recorded.definition(c) for c in constructed],
            "accepted_certificate_sha256": sorted(
                prior_certified
                | {
                    z["certificate_sha256"]
                    for z in result["certificates"]
                    if z["status"] == "CERTIFIED_N_BOUND"
                }
            ),
            "strong": {k: v.snapshot() for k, v in strong_searches.items()},
            "found": {
                k: [
                    {"N_generator": i, "child": x, "parent_word": list(p)}
                    for (i, x), p in v.items()
                ]
                for k, v in found.items()
            },
            "session_history": history[-15:] + [clock.record()],
            "session_count": (checkpoint or {}).get("session_count", 0) + 1,
            "timing_history_truncated": max(
                0, (checkpoint or {}).get("session_count", 0) + 1 - 16
            ),
            "native_Index_tables": "NOT_SAVED_NO_NATIVE_RESUME",
        }
        z["payload_sha256"] = digest(z)

        if len(json.dumps(z).encode()) > L["output_bytes"]:
            raise Limit("N_CHECKPOINT_OUTPUT_CAP")
        result["checkpoint"] = z
        if checkpoint_writer:
            checkpoint_writer(z)

    def completion():
        for candidate in constructed:
            a.deadline = end
            f = found.setdefault(candidate.key, {})
            with clock.phase("insertion_completion"):
                for i, n in enumerate(candidate.cover.N, 1):
                    for x in range(a.d):
                        if (i, x) not in f:
                            p = completion_sharing.lookup(P, n, x)
                            if p is not None:
                                f[i, x] = p
                if (
                    candidate.family in ["universal_mod_2", "involution_derived"]
                    and len(f) < len(candidate.cover.N) * a.d
                ):
                    more, _ = P.mod2_completion(candidate.cover)
                    for key, p in more.items():
                        if key not in f:
                            P.verify_insertion(candidate.cover.N[key[0] - 1], p, key[1])
                            f[key] = p
            row = next(
                z
                for z in result["candidates"]
                if z.get("candidate_key") == candidate.key
            )
            row["found"] = len(f)
            row["required"] = len(candidate.cover.N) * a.d
            row["unmet_targets"] = [
                {"N_generator": i, "child": x}
                for i in range(1, len(candidate.cover.N) + 1)
                for x in range(a.d)
                if (i, x) not in f
            ]
            if L["strength"] in ["strong", "both"]:
                with clock.phase("strong_N_word_insertion"):
                    ss = strong_searches[candidate.key]
                    ss.reuse_weak_proofs(f)
                    ss.step(P, L["N_word_batch"])
                    row["strong_found"] = len(ss.found)
                    row["strong_required"] = row["required"]
                    row["strong_unmet_targets"] = ss.snapshot()["unmet"]
            if len(f) != row["required"] and (
                L["strength"] == "weak"
                or len(strong_searches[candidate.key].found) != row["required"]
            ):
                continue
            strengths = (
                ["weak", "strong"] if L["strength"] == "both" else [L["strength"]]
            )
            for strength in strengths:
                with clock.phase("certificate_assembly"):
                    cert = assemble(
                        candidate,
                        G,
                        P,
                        f,
                        strength,
                        L,
                        strong_proofs=(
                            strong_searches[candidate.key].found
                            if strength == "strong"
                            else None
                        ),
                    )
                if cert is None:
                    row["strong_membership"] = "UNPROVED_FOR_SOME_PARENTS"
                    continue
                cert_key = (candidate.key, strength, digest(cert))
                if any(
                    (z["candidate_key"], z["strength"], z["certificate_sha256"])
                    == cert_key
                    for z in result["certificates"]
                ):
                    continue
                if remaining() <= 0:
                    return False
                z = check_and_raw(action, cert, strength, L, clock, remaining)
                z.update(
                    candidate_key=candidate.key,
                    candidate_family=candidate.family,
                    discovery_mode=(
                        "CHECKPOINT_CERTIFICATE_REPLAY_NOT_NEW_DISCOVERY"
                        if digest(cert) in prior_certified
                        else result["discovery_mode"]
                    ),
                    warm_replay=digest(cert) in prior_certified,
                    newly_completed_certificate=digest(cert) not in prior_certified,
                )
                result["certificates"].append(z)
                if z["status"] == "CERTIFIED_N_BOUND":
                    result["status"] = "CERTIFIED_N_BOUND"
                    result.setdefault(
                        "first_certified_bound_wall_seconds",
                        time.monotonic() - clock.started,
                    )
                    clock.first_certified_bound_wall_seconds = result[
                        "first_certified_bound_wall_seconds"
                    ]
            required_strengths = (
                {"weak", "strong"} if L["strength"] == "both" else {L["strength"]}
            )
            accepted_strengths = {
                z["strength"]
                for z in result["certificates"]
                if z["candidate_key"] == candidate.key
                and z["status"] == "CERTIFIED_N_BOUND"
            }
            if required_strengths <= accepted_strengths:
                return True
        return False

    try:
        with clock.phase("basis_generation"):
            a = SearchAction(action.packet, L)
            a.deadline = end
            original_tick = a.tick

            def external_tick():
                original_tick()
                if progress:
                    progress(
                        {
                            "phase": "N_DISCOVERY_AND_PROOF_COMPLETION",
                            "searched_words": processed,
                            "N_candidates": result["candidates"],
                            "tuple_pool_count": len(P.tuple_records) if P else 0,
                        }
                    )

            a.tick = external_tick
            B, G, result["basis"] = obtain(a, L, basis_hint)
        with clock.phase("candidate_generation_and_normal_cover"):
            restored_definitions = (checkpoint or {}).get("candidate_definitions")
            if restored_definitions:
                for data in restored_definitions:
                    a.deadline = end
                    candidate = recorded.restore(a, B, G, data, L)
                    v = verify_subgroup_certificate(
                        action.packet,
                        candidate.certificate,
                        {
                            "seconds": min(L["verify_seconds"], remaining()),
                            "identity_states": L["identity_states"],
                        },
                    )
                    need(
                        v["status"] != "FAIL",
                        "RESTORED_NORMAL_COVER_PROOF_FAIL:" + str(v),
                    )
                    if v["status"] == "UNKNOWN":
                        result["reason"] = (
                            "RESTORED_NORMAL_COVER_RECHECK_RESOURCE_LIMIT"
                        )
                        return result
                    result["candidates"].append(
                        {
                            "family": candidate.family,
                            "candidate_key": candidate.key,
                            "normal_cover": v,
                            "construction": candidate.construction,
                            "found": 0,
                            "required": len(candidate.cover.N) * a.d,
                            "normal_cover_origin": "BOUND_CHECKPOINT_PROOF_RECHECKED_NO_REENUMERATION",
                        }
                    )
                    if v["status"] == "PASS_SUBGROUP_DATA":
                        constructed.append(candidate)
            else:
                for family in specs(L, len(B)):
                    a.deadline = min(
                        end, time.monotonic() + L["candidate_build_seconds"]
                    )
                    try:
                        t_candidate = time.monotonic()
                        candidate = formal(a, B, G, family, L)
                        candidate_wall = time.monotonic() - t_candidate
                        t_cover_check = time.monotonic()
                        v = verify_subgroup_certificate(
                            action.packet,
                            candidate.certificate,
                            {
                                "seconds": min(L["verify_seconds"], remaining()),
                                "identity_states": L["identity_states"],
                            },
                        )
                        need(v["status"] != "FAIL", "N_COVER_VERIFIER_FAIL:" + str(v))
                        row = {
                            "family": family,
                            "candidate_key": candidate.key,
                            "normal_cover": v,
                            "construction": candidate.construction,
                            "candidate_and_normal_cover_wall_seconds": candidate_wall,
                            "normal_cover_checker_wall_seconds": time.monotonic()
                            - t_cover_check,
                            "found": 0,
                            "required": len(candidate.cover.N) * a.d,
                        }
                        result["candidates"].append(row)
                        if v["status"] == "PASS_SUBGROUP_DATA":
                            constructed.append(candidate)
                    except Limit as e:
                        result["candidates"].append(
                            {"family": family, "status": "UNKNOWN", "reason": str(e)}
                        )
                for seed_strategy, seeds in normal_seed_specs(B, L)[
                    : max(0, L["candidate_limit"] - len(result["candidates"]))
                ]:
                    a.deadline = min(
                        end, time.monotonic() + L["candidate_build_seconds"]
                    )
                    try:
                        adapter = None
                        if L["index_backend"] == "gap_felsch" and not (
                            checkpoint or {}
                        ).get("candidate_definitions"):
                            need(raw_export is not None, "N_FELSCH_RAW_EXPORT_PATH")
                            adapter = lambda aa, bb, gg, nn, ll, cc: native.gap_cover(
                                aa,
                                bb,
                                gg,
                                nn,
                                ll,
                                cc,
                                runner,
                                {
                                    "identity": action.identity.record(),
                                    "kind": "N_NORMAL_CLOSURE_FELSCH",
                                    "verified_relators_basis": [],
                                },
                                raw_export,
                            )
                        candidate = normal_closure(a, B, G, seeds, L, adapter)
                        candidate.construction["seed_strategy"] = seed_strategy
                        v = verify_subgroup_certificate(
                            action.packet,
                            candidate.certificate,
                            {
                                "seconds": min(L["verify_seconds"], remaining()),
                                "identity_states": L["identity_states"],
                            },
                        )
                        need(
                            v["status"] != "FAIL", "NORMAL_CLOSURE_COVER_FAIL:" + str(v)
                        )
                        result["candidates"].append(
                            {
                                "family": candidate.family,
                                "candidate_key": candidate.key,
                                "normal_cover": v,
                                "construction": candidate.construction,
                                "found": 0,
                                "required": len(candidate.cover.N) * a.d,
                            }
                        )
                        if v["status"] == "PASS_SUBGROUP_DATA":
                            constructed.append(candidate)
                    except Limit as e:
                        result["candidates"].append(
                            {
                                "family": "normal_closure",
                                "status": "UNKNOWN",
                                "reason": str(e),
                            }
                        )
        if not constructed:
            result["reason"] = "NO_PROVED_NORMAL_COVER_WITHIN_LIMITS"
            return result
        if L["index_backend"] == "gap_felsch" and not (checkpoint or {}).get(
            "candidate_definitions"
        ):
            for c in constructed:
                if c.family == "normal_closure":
                    continue
                with clock.phase("native_felsch_cover"):
                    mf = {
                        "identity": action.identity.record(),
                        "kind": "N_FELSCH_COVER",
                        "candidate_key": c.key,
                        "verified_relators_basis": native.cover_relators(c, G),
                    }
                    c.certificate = native.gap_cover(
                        a, B, G, c.cover.N, L, c.cover, runner, mf, raw_export
                    )
                result["native_calls"] += 1
        if L["index_backend"] == "native_index" and not (checkpoint or {}).get(
            "candidate_definitions"
        ):
            for c in constructed:
                with clock.phase("native_index"):
                    v = native.execute_index(
                        action,
                        c,
                        runner,
                        {
                            "identity": action.identity.record(),
                            "candidate_key": c.key,
                            "N_generators": c.certificate["N_generators"],
                            "kind": "N_NATIVE_INDEX",
                        },
                        clock,
                    )
                result["native_calls"] += 1
                next(
                    z for z in result["candidates"] if z.get("candidate_key") == c.key
                )["native_index"] = v
        a.deadline = end
        P = InsertionPool(a, B, G, L)
        if checkpoint:
            with clock.phase("restore"):
                P.restore(checkpoint["pool"])
                cursor = checkpoint["word_cursor"]
                processed = checkpoint["stream_words_processed"]
                seed_cursor = checkpoint["root_seed_cursor"]
                seed_complete = checkpoint["root_seeds_complete"]
                history = checkpoint["session_history"]
                valid = {c.key: c for c in constructed}
                for k, rs in checkpoint["found"].items():
                    need(k in valid, "N_CHECKPOINT_CANDIDATE_CHANGED")
                    found[k] = {}
                    for z in rs:
                        i, x = z["N_generator"], z["child"]
                        need(
                            1 <= i <= len(valid[k].cover.N) and 0 <= x < a.d,
                            "N_CHECKPOINT_TARGET_INDEX",
                        )
                        P.verify_insertion(valid[k].cover.N[i - 1], z["parent_word"], x)
                        found[k][i, x] = tuple(z["parent_word"])
        if L["strength"] in ["strong", "both"]:
            for c in constructed:
                strong_searches[c.key] = StrongSearch(
                    c, a, G, L, (checkpoint or {}).get("strong", {}).get(c.key)
                )
        for c in constructed:
            P.set_targets((x, n) for n in c.cover.N for x in range(a.d))
        restore_complete = True
        if not checkpoint and retained_parents:
            with clock.phase("selected_retained_parent_import"):
                for parent in retained_parents:
                    P.observe(parent, "selected_pinned_retained_tuple_parent")
        if completion():
            return result
        if not seed_complete:
            with clock.phase("root_schreier_seeds"):
                for index, p in enumerate(root_seeds(a, B, L)):
                    if index < seed_cursor:
                        continue
                    P.observe(p, "root_schreier_seed")
                    P.observe(inv(p), "root_schreier_seed_inverse")
                    seed_cursor = index + 1
                seed_complete = True
            if completion():
                return result
        invol = all(a.identity(b + b) for b in B)
        for index, w in words(
            len(B), L["word_depth"], max(0, L["word_count"] - processed), cursor, invol
        ):
            a.deadline = end
            with clock.phase("insertion_word_stream"):
                P.observe(expand(w, B), "new_stream_word")
            cursor = index + 1
            processed += 1
            if processed % L["completion_every_words"] == 0:
                if completion():
                    return result
                snapshot()
        completion()
        if L["strength"] in ["strong", "both"]:
            while remaining() > 0 and any(
                ss.processed < L["N_word_count"]
                and len(ss.found) < len(ss.candidate.cover.N) * a.d
                for ss in strong_searches.values()
            ):
                before = sum(ss.processed for ss in strong_searches.values())
                if completion():
                    break
                if sum(ss.processed for ss in strong_searches.values()) == before:
                    break
        if result["status"] == "UNKNOWN":
            result["reason"] = "BOUNDED_WORD_OR_COMPLETION_SEARCH_INCOMPLETE"
    except (Limit, ExportLimit) as e:
        result.update(
            reason=str(e),
            status=(
                "CERTIFIED_N_BOUND"
                if result["certificates"]
                and any(
                    z["status"] == "CERTIFIED_N_BOUND" for z in result["certificates"]
                )
                else "UNKNOWN"
            ),
        )
    except Exception as e:
        result.update(status="ERROR", reason=type(e).__name__ + ": " + str(e))
    finally:
        try:
            if checkpoint and not restore_complete:
                result["checkpoint"] = (
                    copy.deepcopy(checkpoint) if result["status"] == "UNKNOWN" else None
                )
            else:
                snapshot()
        except (Limit, ExportLimit) as e:
            result["checkpoint_limit"] = str(e)
            result["checkpoint"] = None
        except Exception as e:
            result.update(
                status="ERROR", reason="CHECKPOINT_FAILURE:" + str(e), checkpoint=None
            )
        result["completion_optimization"] = completion_sharing.record()
        result["timing"] = clock.record()
        result["timing"]["first_certified_bound_wall_seconds"] = result.get(
            "first_certified_bound_wall_seconds"
        )
        result["new_stream_words_this_invocation"] = processed - (checkpoint or {}).get(
            "stream_words_processed", 0
        )
    return result
