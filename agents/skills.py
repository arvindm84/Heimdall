"""OpenClaw skills: scan a skill before install and quarantine it if it looks malicious.

A skill is a folder with a SKILL.md. `install` copies it to data/skills/<agent>/<name>
when the scan is clean, or to data/skills/quarantine/<name> when it is not.
Only skills named in the agent's permissions are given to the container (`stage`).
"""

import re
import shutil
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parents[1] / "data" / "skills"
QUARANTINE = SKILLS_DIR / "quarantine"
SUPPORTED = ("openclaw",)
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
RULES = [
    ("reads a secrets file", r"\.env\b|\.ssh\b|id_rsa|\.aws/|\.netrc|openclaw\.json|credentials"),
    ("reads keys from the environment", r"printenv|os\.environ|process\.env|\$\{?\w*(KEY|TOKEN|SECRET)\b"),
    ("sends data out", r"\b(curl|wget|nc|ncat|scp)\b|fetch\(|requests\.(get|post)|urllib"),
    ("hides what it runs", r"base64\s+(-d|--decode)|\beval\b|\bexec\(|\|\s*(sh|bash)\b"),
    ("tells the agent to deceive", r"ignore (all |any )?(previous|prior) instructions|do not (tell|mention)"),
]


def scan(source: Path) -> list[dict]:
    """Every rule hit in the skill's text files: [{"file", "line", "rule", "text"}]."""
    findings = []
    for file in sorted(p for p in source.rglob("*") if p.is_file()):
        try:
            lines = file.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            findings.append({"file": file.name, "line": 0, "rule": "not readable text", "text": ""})
            continue
        for number, line in enumerate(lines, 1):
            for rule, pattern in RULES:
                if re.search(pattern, line, re.IGNORECASE):
                    rel = file.relative_to(source).as_posix()
                    findings.append({"file": rel, "line": number, "rule": rule, "text": line.strip()[:200]})
    return findings


def install(agent: str, source: str | Path, force: bool = False) -> dict:
    """Scan and install. Returns {"name", "status": "installed" | "quarantined", "findings"}."""
    if agent not in SUPPORTED:
        raise ValueError(f"{agent} does not support skills")
    source = Path(source).expanduser().resolve()
    name = source.name.lower()
    if not (source / "SKILL.md").is_file():
        raise ValueError(f"{source} has no SKILL.md")
    if not NAME.match(name):
        raise ValueError(f"bad skill name: {name}")
    findings = scan(source)
    status = "quarantined" if findings and not force else "installed"
    target = (QUARANTINE if status == "quarantined" else SKILLS_DIR / agent) / name
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(source, target)
    if status == "installed":
        shutil.rmtree(QUARANTINE / name, ignore_errors=True)
    return {"name": name, "status": status, "findings": findings}


def installed(agent: str) -> list[str]:
    folder = SKILLS_DIR / agent
    return sorted(p.name for p in folder.iterdir() if p.is_dir()) if folder.exists() else []


def stage(agent: str, names: list[str]) -> Path:
    """Fresh folder holding only the allowed, installed skills; mounted read only into the agent."""
    missing = [name for name in names if name not in installed(agent)]
    if missing:
        raise ValueError(f"skills not installed (or quarantined): {', '.join(missing)}")
    staged = SKILLS_DIR.parent / "agents" / f"{agent}-skills"
    shutil.rmtree(staged, ignore_errors=True)
    staged.mkdir(parents=True)
    for name in names:
        shutil.copytree(SKILLS_DIR / agent / name, staged / name)
    return staged
