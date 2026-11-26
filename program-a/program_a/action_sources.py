"""f → A boundary: load an existing pinned action; no generic PCF solver."""

from dataclasses import dataclass
from .contracts import read_pinned, identify, need


@dataclass
class StoredAction:
    packet: dict
    identity: object
    source: dict


def load(ref):
    packet = read_pinned(ref)
    return StoredAction(packet, identify(packet), ref)


def from_polynomial(*args, **kwargs):
    raise NotImplementedError("PHASE1_STORED_ACTION_ADAPTER_ONLY_NO_GENERIC_F_TO_A")


def bind(action, value):
    action.identity.require_match(value.get("identity"))
    return value
