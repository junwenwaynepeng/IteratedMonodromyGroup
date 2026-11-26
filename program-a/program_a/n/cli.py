"""Explicit N invocation only. Native/resource execution must be supplied by a bound host adapter."""

import argparse, json, time
from pathlib import Path
from ..action_sources import load
from ..contracts import pin
from .api import execute


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("action")
    p.add_argument("config")
    p.add_argument("--output", required=True)
    a = p.parse_args(argv)
    start = time.monotonic()
    action = load(pin(a.action))
    config = json.loads(Path(a.config).read_text())
    result = execute(action, config)
    result["outer_invocation_wall_seconds"] = time.monotonic() - start
    Path(a.output).write_text(json.dumps(result, indent=2) + "\n")
    return (
        0
        if result["status"] == "CERTIFIED_N_BOUND"
        else 2 if result["status"] == "ERROR" else 3
    )


if __name__ == "__main__":
    raise SystemExit(main())
