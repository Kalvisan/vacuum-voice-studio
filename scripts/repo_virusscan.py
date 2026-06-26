#!/usr/bin/env python3
"""Validate repository source for suspicious code and accidental secrets."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

SCAN_ROOTS = (
    ROOT_DIR / "scripts",
    ROOT_DIR / "web",
    ROOT_DIR / "assets",
    ROOT_DIR / "docs",
    ROOT_DIR / "config",
)
SCAN_FILES = (
    ROOT_DIR / "x20-voice-tool.sh",
    ROOT_DIR / "README.md",
    ROOT_DIR / "SECURITY.md",
    ROOT_DIR / "CONTRIBUTING.md",
    ROOT_DIR / "requirements.txt",
)

SKIP_DIR_NAMES = {"__pycache__", ".git", "workspace", "output", "node_modules"}
TEXT_SUFFIXES = {".py", ".sh", ".js", ".html", ".css", ".md", ".json", ".csv", ".txt", ".example"}

ALLOWED_URL_HOST_RE = re.compile(
    r"^("
    r"127\.0\.0\.1|localhost|"
    r"([a-z0-9-]+\.)*xiaomi\.com|"
    r"([a-z0-9-]+\.)*mi\.com|"
    r"([a-z0-9-]+\.)*io\.mi\.com"
    r")$",
    re.IGNORECASE,
)

SECRET_PATTERNS = (
    (re.compile(r'"serviceToken"\s*:\s*"(?!YOUR_)[^"]{8,}"'), "Live serviceToken in a tracked file"),
    (re.compile(r'"ssecurity"\s*:\s*"(?!YOUR_)[^"]{8,}"'), "Live ssecurity in a tracked file"),
    (re.compile(r'"userId"\s*:\s*"(?!YOUR_)[0-9]{6,}"'), "Live userId in a tracked file"),
)

SUSPICIOUS_PATTERNS = (
    (re.compile(r"\beval\s*\("), "eval() call"),
    (re.compile(r"\bexec\s*\("), "exec() call"),
    (re.compile(r"compile\s*\([^)]*['\"]exec['\"]"), "compile(..., 'exec')"),
    (re.compile(r"os\.system\s*\("), "os.system() call"),
    (re.compile(r"subprocess\.[A-Za-z_]+\([^)]*shell\s*=\s*True"), "subprocess with shell=True"),
    (re.compile(r"pickle\.loads?\s*\("), "pickle load"),
    (re.compile(r"base64\.b64decode\s*\([^)]+\)\s*\.decode"), "base64 decode to string"),
)

URL_RE = re.compile(r"https?://([A-Za-z0-9._-]+(?::[0-9]+)?)(?:/[^\s\"'`)]*)?", re.IGNORECASE)


@dataclass
class Finding:
    severity: str
    check: str
    path: str
    detail: str


@dataclass
class ScanReport:
    ok: bool
    scanned_files: int = 0
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, severity: str, check: str, path: Path | str, detail: str) -> None:
        self.findings.append(Finding(severity, check, str(path), detail))
        if severity == "error":
            self.ok = False


def iter_scan_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        if root.is_file():
            files.append(root)
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.name in {".connection-ok", "config.json"} or ".bak" in path.name:
                continue
            if path.suffix.lower() in TEXT_SUFFIXES or path.name.endswith(".example"):
                files.append(path)
    for path in SCAN_FILES:
        if path.is_file():
            files.append(path)
    return sorted(set(files))


def check_urls(path: Path, text: str, report: ScanReport) -> None:
    for match in URL_RE.finditer(text):
        host = match.group(1).split(":")[0]
        if not ALLOWED_URL_HOST_RE.match(host):
            report.add(
                "error",
                "network",
                path,
                f"Unexpected outbound URL host: {host} ({match.group(0)})",
            )


def check_patterns(path: Path, text: str, report: ScanReport) -> None:
    if path.name == "repo_virusscan.py":
        return
    for pattern, label in SECRET_PATTERNS:
        if pattern.search(text):
            report.add("error", "secret", path, label)
    for pattern, label in SUSPICIOUS_PATTERNS:
        if pattern.search(text):
            report.add("warning", "pattern", path, label)


def scan_tree(report: ScanReport) -> None:
    for path in iter_scan_files():
        report.scanned_files += 1
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            report.add("error", "binary", path, "Non-text file in scanned source tree")
            continue
        check_urls(path, text, report)
        if path.suffix.lower() in {".py", ".sh", ".js"}:
            check_patterns(path, text, report)


def scan_requirements(report: ScanReport) -> None:
    req = ROOT_DIR / "requirements.txt"
    if not req.exists():
        return
    for line in req.read_text(encoding="utf-8").splitlines():
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        if "==" not in item and not re.match(r"^[A-Za-z0-9_.-]+\[[^\]]+\]==", item):
            report.add(
                "warning",
                "dependencies",
                req,
                f"Unpinned dependency: {item} (consider pinning for reproducible installs)",
            )


def scan_gitignore(report: ScanReport) -> None:
    gitignore = ROOT_DIR / ".gitignore"
    if not gitignore.exists():
        report.add("error", "privacy", gitignore, ".gitignore is missing")
        return
    text = gitignore.read_text(encoding="utf-8")
    for rule in ("config/config.json", "config/.connection-ok", "workspace/", "output/"):
        if rule not in text:
            report.add("error", "privacy", gitignore, f"Missing gitignore rule: {rule}")


def maybe_clamscan(report: ScanReport) -> None:
    import shutil
    import subprocess

    if shutil.which("clamscan") is None:
        report.notes.append("ClamAV not installed — skipped antivirus file scan.")
        return

    targets = [str(path) for path in SCAN_ROOTS if path.exists()] + [
        str(path) for path in SCAN_FILES if path.is_file()
    ]
    proc = subprocess.run(
        ["clamscan", "-r", "--infected", "--no-summary", *targets],
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
    )
    if proc.returncode == 1:
        for line in (proc.stdout or "").splitlines():
            if line.strip():
                report.add("error", "clamav", ROOT_DIR, line.strip())
    elif proc.returncode not in (0, 1):
        report.notes.append(f"ClamAV scan skipped: {proc.stderr.strip() or proc.stdout.strip()}")


def run_scan(*, use_clamav: bool = False) -> ScanReport:
    report = ScanReport(ok=True)
    scan_gitignore(report)
    scan_tree(report)
    scan_requirements(report)
    if use_clamav:
        maybe_clamscan(report)
    else:
        report.notes.append("Run with --clamav to enable optional ClamAV scan.")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan repository source for suspicious code.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    parser.add_argument("--clamav", action="store_true", help="Also run clamscan if installed.")
    args = parser.parse_args(argv)

    report = run_scan(use_clamav=args.clamav)
    payload = {
        "ok": report.ok,
        "scanned_files": report.scanned_files,
        "errors": [asdict(item) for item in report.findings if item.severity == "error"],
        "warnings": [asdict(item) for item in report.findings if item.severity == "warning"],
        "notes": report.notes,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Scanned {report.scanned_files} files.")
        for item in report.findings:
            print(f"[{item.severity.upper()}] {item.check}: {item.path} — {item.detail}")
        for note in report.notes:
            print(f"[note] {note}")
        print("OK — no blocking issues found." if report.ok else "FAILED — fix errors above.")

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
