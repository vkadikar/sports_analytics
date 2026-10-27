"""
Skills: markdown playbooks for recurring kinds of questions (a matchup preview,
a player deep-dive, ...), in skills/<name>.md.

Each file starts with a frontmatter block:

    ---
    name: matchup_analysis
    description: One line saying when to use it.
    ---
    Step-by-step instructions...

Only the names and descriptions go in the system prompt (skill_index()). The
model loads a skill's full instructions with the load_skill tool when a
question fits, so adding skills doesn't bloat every request.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

SKILLS_DIR = Path(__file__).resolve().parent / "skills"


def _parse(path: Path) -> Dict[str, str]:
    text = path.read_text(encoding="utf-8")
    meta: Dict[str, str] = {}
    body = text
    if text.startswith("---"):
        header, _, body = text[3:].partition("\n---")
        for line in header.strip().splitlines():
            key, sep, value = line.partition(":")
            if sep:
                meta[key.strip()] = value.strip()
    return {
        "name": meta.get("name", path.stem),
        "description": meta.get("description", ""),
        "instructions": body.strip(),
    }


def load_skills() -> Dict[str, Dict[str, str]]:
    """{name: {"name", "description", "instructions"}} for every skills/*.md file."""
    skills = (_parse(p) for p in sorted(SKILLS_DIR.glob("*.md")))
    return {s["name"]: s for s in skills}


def skill_index() -> str:
    """The skills section appended to the system prompt: one line per skill."""
    skills = load_skills()
    if not skills:
        return ""
    lines = "\n".join(f"- `{s['name']}`: {s['description']}" for s in skills.values())
    return (
        "## Skills\n\n"
        "You have playbooks for the common kinds of questions, listed below. Before you call any "
        "other tool, check whether the question matches one of them. If it does, your first tool "
        "call must be `load_skill` with that skill's name, and you then follow its steps and "
        "answer format. This applies even when you think you already know which tools to call: "
        "the playbook also says what to compare and what not to claim. Only when a question "
        "matches none of these do you go straight to the other tools.\n\n" + lines
    )
