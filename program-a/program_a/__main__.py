"""Command-line interface for a single supplied action."""

import argparse
import json
from pathlib import Path

from . import fr
from .action_sources import load
from .contracts import pin
from .kh import cover, index
from .n.engine import run
from .shared.exact import Limit


def read(path):
    return json.loads(Path(path).read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    methods = parser.add_subparsers(required=True, dest="method")
    for name, help_text in [
        ("kh", "enumerate a direct-image cover and replay its certificate"),
        ("replay", "check a saved KH certificate with two interpreters"),
        ("n", "search for a normal cover and supported lifts"),
        ("index", "write a GAP script for the direct-product subgroup index"),
        ("fr", "write a GAP script for the FR branching predicates"),
    ]:
        command = methods.add_parser(name, help=help_text)
        command.add_argument("action", type=Path)
        if name == "kh":
            command.add_argument("pool", type=Path)
            command.add_argument("--cosets", type=int, default=4096)
            command.add_argument(
                "--seconds", type=int, default=60, help="NEWTC subprocess timeout"
            )
        if name == "replay":
            command.add_argument("certificate", help="certificate or saved KH result")
        if name == "index":
            group = command.add_mutually_exclusive_group(required=True)
            group.add_argument("--pool", type=Path)
            group.add_argument("--full-h", action="store_true")
        if name == "n":
            command.add_argument(
                "--limits",
                type=Path,
                help="JSON overrides for the Python normal-cover search",
            )
    args = parser.parse_args()
    if not __debug__:
        parser.error("run Python without -O to enable proof checks")
    action = load(pin(args.action))
    if args.method in ("index", "fr"):
        source = (
            fr.render(action.packet)
            if args.method == "fr"
            else index.render(
                action.packet,
                read(args.pool)["tuple_generators"] if args.pool else None,
            )
        )
        print(source, end="")
        return 0
    if args.method == "kh":
        if args.seconds <= 0:
            parser.error("--seconds must be positive")
        try:
            result = cover.solve(
                action.packet, read(args.pool), cosets=args.cosets, seconds=args.seconds
            )
        except Limit as exc:
            result = {"status": "UNKNOWN", "reason": str(exc)}
    elif args.method == "replay":
        saved = read(args.certificate)
        result = cover.replay(action.packet, saved.get("certificate", saved))
    else:
        limits = read(args.limits) if args.limits else {}
        if limits.get("index_backend", "normal_cover") != "normal_cover":
            parser.error("the standalone N command supports the normal_cover backend")
        result = run(action, limits)
    print(json.dumps(result, indent=2))
    return 0 if result["status"].startswith(("PASS", "CERTIFIED")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
