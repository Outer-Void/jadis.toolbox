"""Result model shared by every command. Human and JSON output both render from these objects."""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field
from typing import Any

UNKNOWN = "unknown"


class ExitCode(enum.IntEnum):
    """The `jadis` exit-code contract (documented in docs/cli.md)."""

    OK = 0
    VERIFICATION_FAILED = 1  # the machine was inspected and something required is FAIL
    USAGE = 2  # bad arguments, unknown profile, malformed input file
    UNSUPPORTED = 3  # the environment is not supported for this operation
    INCOMPLETE = 4  # declined, not authorized, partially applied, or interrupted
    INTERNAL = 70  # a bug in jadis


class Status(str, enum.Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"
    UNKNOWN = "UNKNOWN"


class Severity(str, enum.Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Check:
    """One doctor finding. PASS always carries the evidence it rests on."""

    check_id: str
    category: str
    status: Status
    severity: Severity
    summary: str
    detected: Any = None
    expected: Any = None
    evidence: list[str] = field(default_factory=list)
    suggested_fix: str | None = None
    auto_fixable: bool = False
    network: bool = False

    def __post_init__(self) -> None:
        if self.status is Status.PASS and not self.evidence:
            raise ValueError(f"{self.check_id}: PASS requires evidence")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["severity"] = self.severity.value
        return data


@dataclass
class Fact:
    """A detected value plus how it was detected. `value` is UNKNOWN when it could not be determined."""

    value: Any
    source: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"value": self.value, "source": self.source}
        if self.error:
            data["error"] = self.error
        return data


def unknown(source: str, error: str) -> Fact:
    return Fact(UNKNOWN, source, error)
