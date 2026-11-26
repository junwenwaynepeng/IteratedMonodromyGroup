"""Load the GAP internals against which the extraction guards were tested."""

import hashlib
import os
from pathlib import Path

PINS = {
    "sgpres.gi": "0ed9a2a6033e67eb9238c3eb50b701af2b08f52674129bad24c5b4af8321f22e",
    "wordrep.gi": "6c2d78ddf9138b4a3f8bf02da2aa280789ae2f080bbd982b6ab094810ab95f19",
}


def read(name):
    directory = Path(os.environ.get("PROGRAM_A_GAP_LIB", "/usr/share/gap/lib"))
    data = (directory / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != PINS[name]:
        raise ValueError(f"Unrecognized GAP source: {name}")
    return data.decode()
