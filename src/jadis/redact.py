"""Secret redaction. Every human and JSON output passes through `redact_value` before it is printed.

The workstation may hold SSH keys, GitHub tokens, API keys and signing credentials. JADIS therefore:
- never dumps the whole environment: only allow-listed variable *names* are ever reported, and values of
  variables whose names look sensitive are replaced;
- replaces token-shaped strings and private-key blocks wherever they appear, even inside tool output;
- reports the home directory as `~`.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"
SENSITIVE_NAME = re.compile(
    r"(?i)(TOKEN|SECRET|PASSW(OR)?D|PASSPHRASE|API[_-]?KEY|ACCESS[_-]?KEY|PRIVATE|CREDENTIAL|AUTH|COOKIE|SESSION|"
    r"SIGNING|KEYSTORE|_KEY$|^KEY$|DSN|WEBHOOK)"
)
PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?(-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)"), "[REDACTED PRIVATE KEY]"),
    (re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"), REDACTED),
    (re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{16,}\b"), REDACTED),
    (re.compile(r"\b(AKIA|ASIA)[A-Z0-9]{16}\b"), REDACTED),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"), REDACTED),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"), REDACTED),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), REDACTED),
    (re.compile(r"(?i)\b(bearer|token|authorization)\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{12,}"), r"\1=" + REDACTED),
    (re.compile(r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY|PRIVATE_KEY)[A-Z0-9_]*)=([^\s'\"]+)"), r"\1=" + REDACTED),
    (re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@"), r"\1" + REDACTED + "@"),
]


class Redactor:
    def __init__(self, home: str | None = None, secrets: list[str] | None = None):
        self.home = home.rstrip("/") if home and home != "/" else None
        self.secrets = sorted({s for s in (secrets or []) if len(s) >= 6}, key=len, reverse=True)

    @classmethod
    def for_env(cls, env: dict[str, str]) -> Redactor:
        """Values of sensitive-named variables are known secrets wherever they later appear."""
        return cls(env.get("HOME"), [v for k, v in env.items() if SENSITIVE_NAME.search(k)])

    def text(self, value: str) -> str:
        for secret in self.secrets:
            value = value.replace(secret, REDACTED)
        for pattern, repl in PATTERNS:
            value = pattern.sub(repl, value)
        if self.home:
            value = re.sub(re.escape(self.home) + r"(?=/|\b|$)", "~", value)
        return value

    def value(self, data: Any) -> Any:
        if isinstance(data, str):
            return self.text(data)
        if isinstance(data, dict):
            return {k: self.value(v) for k, v in data.items()}
        if isinstance(data, (list, tuple)):
            return [self.value(v) for v in data]
        return data


def env_value(name: str, value: str) -> str:
    """An environment variable's value as it may appear in a report: sensitive names are never shown."""
    return REDACTED if SENSITIVE_NAME.search(name) else value
