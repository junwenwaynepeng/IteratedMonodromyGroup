"""Render native GAP/FR operations on the supplied action."""

from pathlib import Path

from .. import native_gamma
from ..shared.exact import validate_model


def prefix(packet):
    model, _, _ = validate_model(packet)
    return native_gamma.preamble() + native_gamma.original(model)


def render(packet):
    return prefix(packet) + Path(__file__).with_name("branch.g").read_text()
