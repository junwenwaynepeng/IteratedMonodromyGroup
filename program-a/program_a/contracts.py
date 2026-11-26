"""Shared identities and outcome semantics. No computation at import time."""

from dataclasses import dataclass, asdict, replace
from enum import Enum
import hashlib
import json
from pathlib import Path
from .shared.exact import CONVENTION, validate_model, word


class ContractError(ValueError):
    pass


def need(value, message):
    if not value:
        raise ContractError(message)


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def pin(path):
    p = Path(path).resolve()
    return {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def read_pinned(ref):
    need(type(ref) is dict and set(ref) == {"path", "sha256"}, "PIN_SHAPE")
    p = Path(ref["path"])
    need(p.is_absolute() and str(p.resolve()) == str(p), "CANONICAL_SOURCE_PATH")
    raw = p.read_bytes()
    need(hashlib.sha256(raw).hexdigest() == ref["sha256"], "SOURCE_PIN_CHANGED")
    return json.loads(raw)


@dataclass(frozen=True)
class Identity:
    action_id: str
    map_id: str
    table_sha256: str
    model_sha256: str
    packet_sha256: str
    alphabet: str
    rank: int
    degree: int
    convention: str = CONVENTION

    def record(self):
        return asdict(self)

    def require_match(self, other):
        need(self.record() == other, "ACTION_ALPHABET_DEGREE_CONVENTION_MISMATCH")


def identify(packet):
    model, q, d = validate_model(packet)
    need(
        type(packet.get("map_id")) is str and type(packet.get("table_sha256")) is str,
        "STORED_ACTION_IDENTIFIERS_REQUIRED",
    )
    need(packet.get("convention", CONVENTION) == CONVENTION, "ACTION_CONVENTION")
    action_id = packet["map_id"] + ":reference:" + packet["table_sha256"][:16]
    return Identity(
        action_id,
        packet["map_id"],
        packet["table_sha256"],
        digest(model),
        digest(packet),
        action_id + ":original",
        q,
        d,
    )


class Status(str, Enum):
    ExactIndex = "ExactIndex"
    FiniteUpperBound = "FiniteUpperBound"
    Candidate = "Candidate"
    Unknown = "Unknown"
    ResourceLimit = "ResourceLimit"
    Error = "Error"


@dataclass(frozen=True)
class Outcome:
    status: Status
    ambient: str
    subgroup: str
    raw_status: str
    evidence_level: str
    value: int | None = None
    reason: str | None = None
    evidence: tuple = ()
    identity_sha256: str | None = None
    subgroup_sha256: str | None = None

    def __post_init__(self):
        need(isinstance(self.status, Status), "OUTCOME_STATUS")
        if self.status in (Status.ExactIndex, Status.FiniteUpperBound):
            need(type(self.value) is int and self.value > 0, "FINITE_POSITIVE_VALUE")

    def record(self):
        return {
            **asdict(self),
            "status": self.status.value,
            "scientific_certificate": self.evidence_level
            == "WHOLE_TREE_AND_SEPARATE_RAW",
        }

    @classmethod
    def from_record(cls, value):
        v = dict(value)
        v.pop("scientific_certificate", None)
        v["status"] = Status(v["status"])
        v["evidence"] = tuple(v.get("evidence", ()))
        return cls(**v)


def scoped(outcome, action, subgroup_statement):
    """Producer binding, not a proof: bind the raw outcome to its exact input."""
    return replace(
        outcome,
        identity_sha256=digest(action.identity.record()),
        subgroup_sha256=digest(subgroup_statement),
    )


def evidence(ref, identity, claim, subject):
    """Validate a *supplied* receipt's exact correspondence, not its truth afresh.

    The caller declares the trusted receipt source. This is evidence reuse, never
    an independent replay. Claim, action and exact subgroup/statement are pinned.
    """
    z = read_pinned(ref)
    identity.require_match(z.get("identity"))
    need(
        z.get("claim") == claim and z.get("subject_sha256") == digest(subject),
        "EVIDENCE_STATEMENT_OR_SUBGROUP_MISMATCH",
    )
    need(
        z.get("status") == "PASS"
        and z.get("level")
        in ("RECORDED_EXACT_CONSTRUCTION", "WHOLE_TREE", "WHOLE_TREE_AND_SEPARATE_RAW"),
        "MISSING_SUPPORTED_EVIDENCE",
    )
    need(type(z.get("producer")) is str and z["producer"], "EVIDENCE_PRODUCER")
    return {
        "reference": ref,
        "claim": claim,
        "level": z["level"],
        "qualification": "Supplied pinned receipt reused; not independently rerun.",
    }
