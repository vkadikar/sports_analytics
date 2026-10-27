"""
Commish Bot: a small tool-using orchestrator on top of Gemini.

Deliberately simple — no agent framework, no hidden magic. One loop:

    ask Gemini -> read back thought / tool-call / text parts
        -> run any requested tools -> feed results back -> ask again
    ...until Gemini stops calling tools or we hit max_tool_turns.

Each turn's output is returned as a flat list of JSON-serializable "steps"
(thought / tool_call / tool_result / message), in the order they happened,
so a chat UI can render the bot's reasoning and tool use as it goes instead
of only showing the final answer.

The system prompt lives in prompts/commish_bot.md rather than in code, so it
can be edited (or swapped for a different persona/skill) without touching
this file. Tools come from two places: the fantrax_mcp MCP server (league
data, via mcp_client.py) and local Python functions in tools.py.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

from google.genai import types

from .gemini_client import DEFAULT_MODEL, get_client, stream_with_retry
from .mcp_client import get_mcp_client
from .skills import skill_index
from .tools import AVAILABLE_TOOLS

LLM_CLIENT_DIR = Path(__file__).resolve().parent
DEFAULT_SYSTEM_PROMPT_PATH = LLM_CLIENT_DIR / "prompts" / "commish_bot.md"

# Safety valve: how many rounds of "call a tool, then ask again" one message
# can trigger before we give up and tell the user instead of looping forever.
MAX_TOOL_TURNS = 12


class CommishBotAgent:
    """A minimal orchestrator: system prompt (from markdown) + tools + a
    manual function-calling loop that surfaces its intermediate steps."""

    def __init__(
        self,
        system_prompt_path: str | Path = DEFAULT_SYSTEM_PROMPT_PATH,
        tools: Optional[List[Callable[..., Any]]] = None,
        model: str = DEFAULT_MODEL,
        max_tool_turns: int = MAX_TOOL_TURNS,
        use_mcp: bool = True,
    ):
        self.model = model
        self.max_tool_turns = max_tool_turns
        self.system_prompt = "\n\n".join(
            part for part in (Path(system_prompt_path).read_text(encoding="utf-8"), skill_index()) if part
        )
        self.local_tools = {t.__name__: t for t in (AVAILABLE_TOOLS if tools is None else tools)}
        self.use_mcp = use_mcp
        # Filled on first run(), so constructing the agent (at Flask import time) doesn't
        # start the MCP server subprocess.
        self._declarations: Optional[List[types.FunctionDeclaration]] = None
        self._mcp_tool_names: set[str] = set()
        self._mcp_instructions = ""
        self._declarations_lock = threading.Lock()

    def _function_declarations(self) -> List[types.FunctionDeclaration]:
        """Schemas for every tool the model can call: local Python functions plus the
        fantrax_mcp server's tools. If the MCP server can't start, the bot still runs
        with local tools only."""
        with self._declarations_lock:
            if self._declarations is not None:
                return self._declarations
            api_option = "VERTEX_AI" if get_client().vertexai else "GEMINI_API"
            declarations = [
                types.FunctionDeclaration.from_callable_with_api_option(callable=fn, api_option=api_option)
                for fn in self.local_tools.values()
            ]
            if self.use_mcp:
                try:
                    self._mcp_instructions = get_mcp_client().instructions()
                    for tool in get_mcp_client().list_tools():
                        # The v1 API has no parameters_json_schema field, so convert MCP's
                        # JSON Schema into the SDK's Schema type.
                        declarations.append(types.FunctionDeclaration(
                            name=tool.name,
                            description=tool.description or "",
                            parameters=types.Schema.from_json_schema(
                                json_schema=types.JSONSchema.model_validate(tool.input_schema),
                                api_option=api_option,
                            ),
                        ))
                        self._mcp_tool_names.add(tool.name)
                except Exception as e:
                    print(f"Warning: fantrax_mcp tools unavailable, continuing without them: {e}")
            self._declarations = declarations
            return declarations

    def _call_tool(self, name: str, args: Dict[str, Any]) -> Any:
        if name in self._mcp_tool_names:
            return get_mcp_client().call_tool(name, args)
        tool = self.local_tools.get(name)
        if tool is None:
            return {"error": f"Unknown tool: {name}"}
        try:
            return tool(**args)
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _manager_section(manager: Optional[Dict[str, str]]) -> str:
        """Who the user is, from the manager they picked in the chat widget."""
        if not manager:
            return ""
        team_id = f" (Fantrax team ID `{manager['teamId']}`)" if manager.get("teamId") else ""
        return (
            "## Who you're talking to\n\n"
            f"You're talking to **{manager['name']}**, manager of **{manager['team']}**{team_id}. "
            "\"I\", \"me\", \"my team\", and \"my players\" mean this manager and this team, so use "
            "them without asking which team is theirs. Address them by first name now and then, and "
            "make the banter personal to their team's results. They picked this in a dropdown and can "
            "switch mid-conversation; this section is always current, so if earlier messages were "
            "about another team, this one wins."
        )

    def _config(self, manager: Optional[Dict[str, str]] = None) -> types.GenerateContentConfig:
        declarations = self._function_declarations()
        # The MCP server's instructions carry the league's scoring rules.
        parts = (self.system_prompt, self._mcp_instructions, self._manager_section(manager))
        return types.GenerateContentConfig(
            system_instruction="\n\n".join(part for part in parts if part),
            tools=[types.Tool(function_declarations=declarations)] if declarations else None,
            # Manual loop below executes tools itself, step by step, so we can
            # surface each call/result rather than have the SDK hide them.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            thinking_config=types.ThinkingConfig(include_thoughts=True),
        )

    @staticmethod
    def _to_contents(history: Optional[List[Dict[str, str]]]) -> List[types.Content]:
        contents = []
        for turn in history or []:
            role = "model" if turn.get("role") == "assistant" else "user"
            contents.append(types.Content(role=role, parts=[types.Part(text=turn.get("text", ""))]))
        return contents

    def stream(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        manager: Optional[Dict[str, str]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Runs one user turn, yielding events as they happen:

          {"type": "thought", "text": str}  -- a fragment of the model's reasoning
          {"type": "message", "text": str}  -- a fragment of the reply
          {"type": "tool_call", "name": str, "args": dict}
          {"type": "tool_result", "name": str, "result": Any}

        Gemini streams thoughts and text in fragments, so consecutive thought or
        message events belong to the same block; a tool event starts a new one.

        `manager` ({"name", "team", "teamId"}) is who the user is; it goes into the system prompt.
        """
        client = get_client()
        config = self._config(manager)
        contents = self._to_contents(history)
        contents.append(types.Content(role="user", parts=[types.Part(text=message)]))

        for _ in range(self.max_tool_turns):
            model_parts: List[types.Part] = []
            function_calls = []
            chunks = stream_with_retry(
                lambda: client.models.generate_content_stream(model=self.model, contents=contents, config=config)
            )
            for chunk in chunks:
                if not chunk.candidates or not chunk.candidates[0].content:
                    continue
                for part in chunk.candidates[0].content.parts or []:
                    model_parts.append(part)
                    if getattr(part, "function_call", None):
                        function_calls.append(part.function_call)
                    elif getattr(part, "thought", False) and part.text:
                        yield {"type": "thought", "text": part.text}
                    elif part.text:
                        yield {"type": "message", "text": part.text}
            # The full model turn, thought signatures included, goes back into the history
            # so Gemini can continue its reasoning after the tool results.
            contents.append(types.Content(role="model", parts=model_parts))

            if not function_calls:
                return

            response_parts = []
            for fc in function_calls:
                args = dict(fc.args or {})
                yield {"type": "tool_call", "name": fc.name, "args": args}
                result = self._call_tool(fc.name, args)
                yield {"type": "tool_result", "name": fc.name, "result": result}
                response_parts.append(types.Part.from_function_response(name=fc.name, response=result))

            contents.append(types.Content(role="user", parts=response_parts))

        yield {
            "type": "message",
            "text": "I went through a few rounds of tool calls without landing on an answer. "
                    "Try rephrasing that?",
        }

    def run(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        manager: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Runs one user turn to completion and returns its steps, with consecutive thought or
        message fragments merged into one step each. For scripts and tests; the chat uses stream()."""
        steps: List[Dict[str, Any]] = []
        for event in self.stream(message, history, manager):
            last = steps[-1] if steps else None
            if last and event["type"] in ("thought", "message") and last["type"] == event["type"]:
                last["text"] += event["text"]
            else:
                steps.append(dict(event))
        return steps
