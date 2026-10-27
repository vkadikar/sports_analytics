"""
Commish Bot's News page: weekly recaps and previews, written once and cached as markdown files.

Each post is news/gw<NN>-<kind>.md, where kind is "recap" (a finished gameweek) or "preview"
(the next one, written before it starts). A file starts with a frontmatter block:

    ---
    kind: recap
    gameweek: 8
    title: The headline
    published: 2026-10-27T08:30:00-04:00
    model: gemini-3.8-flash
    ---
    Markdown body...

Posts are only ever generated when their file is missing, so a published post never changes
unless someone edits or deletes the file (delete it, or pass --force, to have it rewritten).

Run it from the repo root:

    python3 soccer/league_hub/news.py              # sync, then write whatever is missing
    python3 soccer/league_hub/news.py --dry-run    # show what would be written
    python3 soccer/league_hub/news.py --recap 3 --force

The scheduled GitHub Action (.github/workflows/league-news.yml) runs the first form daily and
commits any new posts, which redeploys the site.
"""

import argparse
import base64
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
SOCCER_DIR = BASE_DIR.parent
NEWS_DIR = BASE_DIR / "news"
LEAGUE_TZ = ZoneInfo("America/New_York")

for path in (SOCCER_DIR.parent, SOCCER_DIR, BASE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

KINDS = ("recap", "preview")

# The recap and preview playbooks take several rounds of tool calls, more than a chat reply needs.
NEWS_MAX_TOOL_TURNS = 20
# Anything shorter than this is the bot failing or bailing out, not a post worth caching.
MIN_BODY_CHARS = 600

PUBLISHING_NOTE = (
    "This goes straight onto the league hub's News page: nobody is chatting with you. Don't ask "
    "questions, offer follow-ups, or mention tools, skills, or data sources. Your reply must start "
    "with a single `# ` headline line (the post's title, no gameweek number needed), then the "
    "write-up using `##` section headers."
)


def recap_prompt(gw: int) -> str:
    return (
        f"Write the weekly recap for gameweek {gw}, using the `gameweek_recap` skill.\n\n"
        f"Write it as if it's the morning after gameweek {gw} finished. The tools may return data "
        f"from later gameweeks: ignore all of it. Use get_standings(through_week={gw}) for the table, "
        f"and work out form and season averages from get_weekly_scores rows up to week {gw} only "
        f"(get_form_table covers the whole season so far, so only use it if {gw} is the latest "
        f"played week). For \"Looking ahead\", use get_matchups({gw + 1}) for the fixtures and don't "
        f"mention how they turned out.\n\n" + PUBLISHING_NOTE
    )


def preview_prompt(gw: int) -> str:
    return (
        f"Write the preview of gameweek {gw}, using the `gameweek_preview` skill. "
        f"Gameweek {gw - 1} is the latest finished week.\n\n" + PUBLISHING_NOTE
    )


def post_path(gw: int, kind: str) -> Path:
    return NEWS_DIR / f"gw{gw:02d}-{kind}.md"


def _parse(path: Path) -> Dict[str, Any]:
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
        "slug": path.stem,
        "kind": meta.get("kind", "recap"),
        "gameweek": int(meta.get("gameweek", 0)),
        "title": meta.get("title", ""),
        "published": meta.get("published", ""),
        "body": body.strip(),
    }


def list_posts() -> List[Dict[str, Any]]:
    """Every cached post, newest first: later gameweeks first, and a week's recap before its preview."""
    posts = [_parse(p) for p in NEWS_DIR.glob("gw*.md")]
    return sorted(posts, key=lambda p: (p["gameweek"], p["kind"] == "recap"), reverse=True)


def _final_text(steps: List[Dict[str, Any]]) -> str:
    """The bot's reply after its last tool call; anything it said before that was thinking aloud."""
    last_tool = max((i for i, s in enumerate(steps) if s["type"] in ("tool_call", "tool_result")), default=-1)
    return "".join(s["text"] for s in steps[last_tool + 1:] if s["type"] == "message").strip()


def _split_title(text: str) -> tuple[str, str]:
    """Pulls the leading `# headline` off the reply."""
    first, _, rest = text.partition("\n")
    if first.startswith("# "):
        return first[2:].strip().strip("*"), rest.strip()
    return "", text


def generate_post(agent, gw: int, kind: str) -> Path:
    """Has Commish Bot write one post and saves it. Raises rather than saving a reply that looks broken."""
    prompt = recap_prompt(gw) if kind == "recap" else preview_prompt(gw)
    text = _final_text(agent.run(prompt))
    title, body = _split_title(text)
    if len(body) < MIN_BODY_CHARS:
        raise RuntimeError(f"GW {gw} {kind}: reply too short to publish ({len(body)} chars): {text[:300]!r}")
    if not title:
        title = f"Gameweek {gw} {kind}"

    published = datetime.now(LEAGUE_TZ).replace(microsecond=0).isoformat()
    header = f"---\nkind: {kind}\ngameweek: {gw}\ntitle: {title}\npublished: {published}\nmodel: {agent.model}\n---\n\n"
    path = post_path(gw, kind)
    NEWS_DIR.mkdir(exist_ok=True)
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(header + body + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def due_posts(completed_gws: List[int], gameweek_dates: Dict[Any, Dict[str, str]], now: datetime) -> List[tuple[int, str]]:
    """(gameweek, kind) for every post that should exist by now but doesn't: a recap for each
    finished gameweek, and a preview of the next one if it hasn't kicked off yet."""
    due = [(gw, "recap") for gw in sorted(completed_gws) if not post_path(gw, "recap").exists()]
    upcoming = max(completed_gws, default=0) + 1
    dates = gameweek_dates.get(upcoming) or gameweek_dates.get(str(upcoming))
    if upcoming <= 38 and dates and now < datetime.fromisoformat(dates["start"]) and not post_path(upcoming, "preview").exists():
        due.append((upcoming, "preview"))
    return due


def _install_cookie_from_env() -> None:
    """Same as app.py: hosted runs (the GitHub Action) pass the Fantrax cookie base64-encoded."""
    if os.getenv("FANTRAX_COOKIE_B64") and not os.getenv("FANTRAX_COOKIE_PATH"):
        cookie_file = Path(tempfile.gettempdir()) / "fantraxloggedin.cookie"
        cookie_file.write_bytes(base64.b64decode("".join(os.environ["FANTRAX_COOKIE_B64"].split()), validate=True))
        os.environ["FANTRAX_COOKIE_PATH"] = str(cookie_file)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Write Commish Bot's missing recaps and previews.")
    parser.add_argument("--recap", type=int, nargs="*", metavar="GW", help="only these recaps")
    parser.add_argument("--preview", type=int, nargs="*", metavar="GW", help="only these previews")
    parser.add_argument("--force", action="store_true", help="rewrite the posts named by --recap/--preview even if cached")
    parser.add_argument("--dry-run", action="store_true", help="list what would be written, without calling Gemini")
    args = parser.parse_args(argv)

    _install_cookie_from_env()
    import sync_data
    sync = sync_data.main()

    if args.recap is not None or args.preview is not None:
        wanted = [(gw, "recap") for gw in args.recap or []] + [(gw, "preview") for gw in args.preview or []]
        unfinished = [gw for gw, kind in wanted if kind == "recap" and gw not in sync["completed_gws"]]
        if unfinished:
            parser.error(f"gameweeks {unfinished} haven't finished yet")
        todo = [(gw, kind) for gw, kind in wanted if args.force or not post_path(gw, kind).exists()]
    else:
        todo = due_posts(sync["completed_gws"], sync["gameweek_dates"], datetime.now(LEAGUE_TZ))

    if not todo:
        print("News is up to date.")
        return 0
    print("To write: " + ", ".join(f"GW {gw} {kind}" for gw, kind in todo))
    if args.dry_run:
        return 0

    from llm_client import CommishBotAgent
    agent = CommishBotAgent(max_tool_turns=NEWS_MAX_TOOL_TURNS)
    failures = 0
    # Each post is saved as soon as it's written, so one failure doesn't lose the others.
    for gw, kind in todo:
        try:
            print(f"Writing GW {gw} {kind}...", flush=True)
            print(f"  saved {generate_post(agent, gw, kind).relative_to(BASE_DIR)}")
        except Exception as e:
            failures += 1
            print(f"  FAILED: {e}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
