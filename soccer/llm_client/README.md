# llm_client

Gemini-backed LLM features for the league hub. Currently just one agent:
**Commish Bot**, the chat widget in the bottom-right corner of the league
hub (`soccer/league_hub`).

```
llm_client/
├── __init__.py            # Exports CommishBotAgent, get_client
├── gemini_client.py        # Shared google-genai client + retry-on-503 helper
├── agent.py                 # CommishBotAgent: the tool-calling orchestrator
├── mcp_client.py            # Persistent client for the fantrax_mcp server
├── skills.py                # Loads skills/*.md and builds the prompt's skill index
├── tools.py                  # Local Python tools (load_skill, run_python)
├── sandbox.py                # Runs run_python scripts in a restricted subprocess
├── sandbox_harness.py        # The subprocess side: checks and runs the script
├── prompts/
│   └── commish_bot.md          # Commish Bot's system prompt (edit this, not the code)
├── skills/                   # One markdown playbook per kind of question
└── test_connection.ipynb         # Standalone smoke test for the Gemini API
```

## Setup

Needs `GEMINI_API_KEY` (an AI Studio key — see `test_connection.ipynb` for how
it was wired up) in `soccer/config/.env`:

```
export GEMINI_API_KEY=your-key-here
```

Override the model with `GEMINI_MODEL` if Google retires the current default
again (see `gemini_client.DEFAULT_MODEL`).

## How the orchestrator works (`agent.py`)

`CommishBotAgent.run(message, history)` runs one manual function-calling loop
against Gemini — no agent framework, so it's easy to read top to bottom:

1. Ask Gemini, with the system prompt from `prompts/commish_bot.md` and the
   tools (see Tools below) available to it.
2. Gemini's response comes back in parts. Each part is one of:
   - a **thought** (`part.thought`) — the model's reasoning, exposed to the
     caller so a chat UI can show "thinking" bubbles;
   - a **function call** — we route it to the MCP server or a local tool and call it with
     the given args, and feed the (JSON) result back to Gemini as a
     `function_response`;
   - plain **text** — the reply.
3. If Gemini asked for tools, we loop back to step 1 with the tool results
   appended to the conversation. Otherwise we're done.

`CommishBotAgent.stream()` streams Gemini's output and yields events as they
happen: `thought` and `message` fragments as the text arrives, and
`tool_call` / `tool_result` around each tool. Consecutive fragments of the
same type belong to one block. `run()` collects the same events into a list
of merged steps, for scripts and tests.

## Tools

The agent's tools come from two sources, merged on the first chat request:

- **The `fantrax_mcp` MCP server** (`soccer/fantrax_mcp/`) provides all the
  league data: standings, efficiency, matchups, rosters, free agents, player
  stat lines, scoring, and so on. Its MCP `instructions` (the league's
  scoring rules) are appended to the system prompt.
  `mcp_client.py` starts the server as a subprocess over stdio on first use
  and keeps the session open. The agent converts each MCP tool's JSON schema
  into a Gemini function declaration and sends calls to those tools back
  through the client. If the server can't start, the bot keeps running
  without those tools.
- **Local Python functions** in `tools.py`, for small helpers that don't
  need a server. Write a type-hinted function with a docstring and add it to
  `AVAILABLE_TOOLS`. The SDK builds the schema from the signature.

To give the bot more league data, add an `@mcp.tool()` to
`soccer/fantrax_mcp/server.py` rather than a local tool.

## Skills

Skills are playbooks for recurring kinds of questions: which tools to call,
what to compare, and how to shape the answer. Each one is a markdown file in
`skills/`:

| Skill | For |
|---|---|
| `matchup_analysis` | Two teams head to head: a preview, a past result, or "who'd win" |
| `player_performance` | One player's output, ownership, and start/trade/pickup value |
| `player_rankings` | Players ranked across the league: best at a position, top scorers, best per game |
| `team_performance` | One team's season: form, luck vs. skill, lineup management, weak spots |
| `power_rankings` | The league ranked by a blend of EWMA, season average, and all-play record, plus form, luck, and volatility |
| `gameweek_recap` | A long write-up of one gameweek: every result, team of the week, blunders, table movement, awards |
| `waiver_analysis` | Pickups and drops: best free agents, trending players, who to cut |
| `trade_analysis` | Who wins a trade, whether it's fair, and trade ideas |
| `lineup_advice` | Start/sit calls for the coming gameweek |
| `manager_roast` | Slagging off a manager with their own numbers |
| `data_analysis` | Custom calculations with `run_python`: streaks, rolling averages, what-ifs |

Only each skill's name and description go into the system prompt. When a
question fits a skill, the model calls the `load_skill` tool to get the full
instructions and then follows them, so adding skills keeps the prompt short.
The chat shows this step as "Using the … playbook".

## Running Python (`run_python`)

The `run_python` tool lets the model run a short pandas/numpy script for analysis the data
tools don't do directly. Inside the script, `tool(name, **args)` calls any `fantrax_mcp`
tool, so large data never has to pass through the model's context.

The script runs in a separate process (`sandbox_harness.py`) with an empty environment, a
temporary working directory, and limits of about 10 seconds of CPU, 90 seconds overall,
and 40 `tool()` calls. Before it runs, the code is checked: imports only from a small list
(pandas, numpy, math, statistics, collections, ...), no underscore attributes, no
`open`/`eval`/`exec`/`getattr`, and no pandas or numpy file readers or writers. After the
imports, resource limits block new processes and writing files.

This is a restricted environment, not a hardened sandbox. It keeps out the obvious ways to
read files, reach secrets, or run commands, but it isn't a security boundary against a
determined attacker. The chat endpoint has no login, so anyone who finds the site can get
the bot to run a script. Set `COMMISH_PYTHON=0` to switch the tool off.

To add a skill, create `skills/<name>.md` with this header:

```
---
name: <name>
description: One line saying which questions it's for.
---
```

followed by the steps. The description is what the model uses to decide
whether the skill applies, so make it specific. New skills are picked up on
the next server restart.

## Changing the persona

Edit `prompts/commish_bot.md`. It's read when the server starts, so a new
persona or tone needs no code changes.

## Served by (`soccer/league_hub/app.py`)

`POST /api/commish-bot/chat` with `{"message": str, "history": [{"role", "text"}, ...],
"manager": {"name", "team", "teamId"}}`
runs one turn and streams its events back as newline-delimited JSON
(`application/x-ndjson`), one event per line. A failure partway through
arrives as a final `{"type": "error", "error": str}` line. A bad request
(missing or overlong message) gets an ordinary JSON 400 instead.

`manager` is required: the widget makes the chatter pick which manager they are before the
input unlocks, and the agent adds a "Who you're talking to" section to the system prompt
for that request. The pick can be changed from the header dropdown at any point. The
greeting after a pick is canned, not generated (`commishGreeting` in `app.js`): it's built
from the manager's standings row, so it's the same every time for the same table. It isn't
sent to the model as history. The pick is self-declared, not a login.

The frontend (`index.html` + `app.js` + `style.css`, search "commish") reads
the stream and renders events as they arrive. Replies and reasoning are
rendered as markdown with `marked`, sanitized with `DOMPurify` (both loaded
from cdnjs). The panel can go full screen from its header, and Escape exits
full screen.
