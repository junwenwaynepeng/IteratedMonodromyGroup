"""Minimal explicit N API; nothing changes in other subgroup or solver modules."""

from .engine import run
from .native import render_index
from .assembly import raw_check
from ..contracts import read_pinned, need, digest


def execute(action, config, *, runner=None, checkpoint_writer=None):
    need(config.get("schema") == "N_method_config_v1", "N_CONFIG_SCHEMA")
    action.identity.require_match(config.get("identity"))
    need(
        not (config.get("checkpoint") and config.get("checkpoint_result")),
        "ONE_N_CHECKPOINT_SOURCE",
    )
    checkpoint = read_pinned(config["checkpoint"]) if config.get("checkpoint") else None
    if config.get("checkpoint_result"):
        old = read_pinned(config["checkpoint_result"])
        action.identity.require_match(old.get("identity"))
        need(
            old.get("schema") == "N_method_result_v1"
            and old.get("checkpoint") is not None,
            "N_RESULT_CHECKPOINT_REQUIRED",
        )
        checkpoint = old["checkpoint"]
    hint = read_pinned(config["basis_hint"]) if config.get("basis_hint") else None
    return run(
        action,
        config.get("limits"),
        basis_hint=hint,
        checkpoint=checkpoint,
        runner=runner,
        raw_export=config.get("raw_export"),
        checkpoint_writer=checkpoint_writer,
    )
