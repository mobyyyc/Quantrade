"""Fail closed when tracked files or Git history contain credential material."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
from typing import Iterable


TEXT_SUFFIXES = {
    "", ".cjs", ".css", ".csv", ".env", ".example", ".html", ".ini", ".js",
    ".json", ".md", ".mjs", ".ps1", ".py", ".sql", ".toml", ".ts", ".tsx",
    ".txt", ".yaml", ".yml",
}
PLACEHOLDERS = {
    "changeme", "ci-placeholder", "example", "password", "postgres", "replace-me",
    "replace-with-alpaca-key", "replace-with-alpaca-secret", "replace-with-local-password",
    "secret", "secret-value", "test", "unused",
}
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
ALPACA_KEY = re.compile(r"\bPK[A-Z0-9]{18,}\b")
TOKEN = re.compile(r"\b(?:gh[opusr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b")
NAMED_ASSIGNMENT = re.compile(
    r"^\s*(APCA_API_KEY_ID|APCA_API_SECRET_KEY|FRED_API_KEY)\s*=\s*['\"]?([^\s'\"]+)",
    re.MULTILINE,
)
POSTGRES_URL = re.compile(r"postgres(?:ql)?://[^:\s/]+:([^@\s/]+)@", re.IGNORECASE)


@dataclass(frozen=True)
class SecretFinding:
    path: str
    rule: str
    line: int


def _placeholder(value: str) -> bool:
    normalized = value.strip().strip("'\"").casefold()
    return normalized in PLACEHOLDERS or normalized.startswith(("replace-", "example-", "ci-"))


def scan_text(path: str, text: str) -> tuple[SecretFinding, ...]:
    findings: list[SecretFinding] = []
    checks: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("private_key", PRIVATE_KEY),
        ("alpaca_key_id", ALPACA_KEY),
        ("access_token", TOKEN),
    )
    for rule, pattern in checks:
        findings.extend(
            SecretFinding(path, rule, text.count("\n", 0, match.start()) + 1)
            for match in pattern.finditer(text)
        )
    for match in NAMED_ASSIGNMENT.finditer(text):
        if not _placeholder(match.group(2)):
            findings.append(SecretFinding(path, f"credential_assignment:{match.group(1)}", text.count("\n", 0, match.start()) + 1))
    for match in POSTGRES_URL.finditer(text):
        if not _placeholder(match.group(1)):
            findings.append(SecretFinding(path, "database_password", text.count("\n", 0, match.start()) + 1))
    return tuple(findings)


def _git(*arguments: str) -> bytes:
    return subprocess.run(["git", *arguments], check=True, capture_output=True).stdout


def _tracked_files() -> tuple[str, ...]:
    return tuple(item.decode("utf-8") for item in _git("ls-files", "-z").split(b"\0") if item)


def _eligible_path(path: str) -> bool:
    return Path(path).suffix.casefold() in TEXT_SUFFIXES


def scan_repository(*, include_history: bool) -> tuple[SecretFinding, ...]:
    findings: set[SecretFinding] = set()
    for path in _tracked_files():
        if not _eligible_path(path):
            continue
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        findings.update(scan_text(path, text))
    if include_history:
        history = _git("log", "--all", "--full-history", "-p", "--no-ext-diff", "--text")
        findings.update(scan_text("<git-history>", history.decode("utf-8", errors="replace")))
    return tuple(sorted(findings, key=lambda item: (item.path, item.line, item.rule)))


def format_findings(findings: Iterable[SecretFinding]) -> str:
    return "\n".join(f"{item.path}:{item.line}: {item.rule}" for item in findings)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan tracked files for secrets without printing their values")
    parser.add_argument("--history", action="store_true", help="scan every reachable historical blob too")
    args = parser.parse_args()
    findings = scan_repository(include_history=args.history)
    if findings:
        parser.exit(1, f"secret_audit=failed; findings={len(findings)}\n{format_findings(findings)}\n")
    print(f"secret_audit=passed; history={str(args.history).lower()}")


if __name__ == "__main__":
    main()
