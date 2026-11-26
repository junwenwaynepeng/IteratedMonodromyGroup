from dataclasses import dataclass


@dataclass(frozen=True)
class NativeReturn:
    stdout: str
    stderr: str
    returncode: int
    export: dict | None = None
    resource_reason: str | None = None
    interrupted: bool = False
