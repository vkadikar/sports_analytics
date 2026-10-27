"""
Local, in-process tools for Commish Bot.

Fantrax league data comes from the fantrax_mcp MCP server instead
(soccer/fantrax_mcp/server.py); agent.py merges those tools in at startup.
This file is for small, Python-only helpers that don't belong behind an MCP
server.

Each tool is a plain, type-hinted Python function with a docstring. The
google-genai SDK turns the signature and docstring into the schema the model
sees. To add one, write the function here and add it to AVAILABLE_TOOLS.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from .mcp_client import get_mcp_client
from .sandbox import run_script
from .skills import load_skills


def load_skill(name: str) -> Dict[str, Any]:
    """Loads the step-by-step playbook for one kind of question. The available skill names
    and when to use each are listed under "Skills" in your instructions.

    Args:
        name: The skill's name, e.g. "matchup_analysis".
    """
    skills = load_skills()
    skill = skills.get(name)
    if skill is None:
        return {"error": f'No skill named "{name}". Available: {", ".join(skills)}'}
    return {"name": skill["name"], "instructions": skill["instructions"]}


def run_python(code: str) -> Dict[str, Any]:
    """Runs a short Python script for data analysis and returns what it prints. Use it for
    calculations the other tools don't do directly: rolling or weighted averages, streaks,
    correlations, custom rankings, simulations, or crunching a large tool result. The
    `data_analysis` skill explains how to write one.

    Inside the script:
    - `pd` (pandas) and `np` (numpy) are already imported. You can also import math,
      statistics, itertools, collections, functools, datetime, random, heapq, bisect, decimal,
      fractions, re, and json. Nothing else, and no files, network, or underscore attributes.
    - `tool(name, **args)` calls any league data tool by name and returns its result dict,
      e.g. `tool("get_weekly_scores")["rows"]` or `tool("get_free_agents", position="M")`.
      Data fetched this way doesn't pass through your context, so prefer it to pasting data in.
    - Print what you want to see. If the last line is an expression, its value is shown too.
      Output is capped at about 12,000 characters, so print summaries, not whole tables.

    Limits: about 10 seconds of CPU and 90 seconds overall, at most 40 tool() calls.

    Args:
        code: The Python script.
    """
    client = get_mcp_client()
    return run_script(code, client.call_tool, (t.name for t in client.list_tools()))


AVAILABLE_TOOLS = [load_skill] + ([run_python] if os.getenv("COMMISH_PYTHON", "1") != "0" else [])
