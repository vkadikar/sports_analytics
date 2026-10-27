"""
Persistent MCP client Commish Bot uses to call the fantrax_mcp server's tools
(soccer/fantrax_mcp/server.py).

The `mcp` SDK is async, but CommishBotAgent.run() is called synchronously
from Flask. Rather than start a fresh server subprocess per tool call (paying
the pandas/fantrax_wrapper import cost every time), this starts the server
once on a background thread with its own event loop and keeps the session
open for the life of the process. Each sync call hops onto that loop and
waits for the result.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Dict, List

from mcp import ClientSession, types
from mcp.client.stdio import StdioServerParameters, stdio_client

SOCCER_DIR = Path(__file__).resolve().parent.parent


class FantraxMCPClient:
    """Starts `python -m fantrax_mcp.server` over stdio on first use."""

    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True, name="fantrax-mcp-loop")
        self._thread.start()
        self._session: ClientSession | None = None
        self._instructions: str | None = None
        # Keeps the stdio transport and session context managers alive; entered without a live
        # reference they get garbage-collected and close the pipe under the session.
        self._exit_stack = AsyncExitStack()
        self._init_lock = threading.Lock()

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    async def _connect(self) -> ClientSession:
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "fantrax_mcp.server"],
            cwd=str(SOCCER_DIR),
            # The SDK only passes a few safe vars (HOME, PATH, ...) to the subprocess. Forward the
            # Fantrax config too, or on Render the server never sees the decoded cookie's path.
            env={k: v for k, v in os.environ.items() if k in ("FANTRAX_COOKIE_PATH", "FANTRAX_LEAGUE_ID")},
        )
        read, write = await self._exit_stack.enter_async_context(stdio_client(server_params))
        session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        self._instructions = (await session.initialize()).instructions
        return session

    def _ensure_session(self) -> ClientSession:
        with self._init_lock:
            if self._session is None:
                self._session = self._run(self._connect())
        return self._session

    def instructions(self) -> str:
        """The server's instructions (the league's scoring rules), for the system prompt."""
        self._ensure_session()
        return self._instructions or ""

    def list_tools(self) -> List[types.Tool]:
        """The server's tool definitions (name, description, input JSON schema)."""
        return self._run(self._ensure_session().list_tools()).tools

    def call_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Calls one tool and returns its result dict ({"error": ...} on failure)."""
        try:
            result = self._run(self._ensure_session().call_tool(name, args))
        except Exception as e:
            return {"error": f"fantrax_mcp call failed: {e}"}

        if result.structured_content is not None:
            # MCPServer wraps a dict return value as {"result": <dict>} in structured content.
            content = result.structured_content
            if set(content) == {"result"} and isinstance(content["result"], dict):
                return content["result"]
            return content
        for block in result.content or []:
            text = getattr(block, "text", None)
            if text:
                try:
                    return json.loads(text)
                except ValueError:
                    return {"result": text}
        return {"error": "fantrax_mcp returned an empty result"}


_client: FantraxMCPClient | None = None


def get_mcp_client() -> FantraxMCPClient:
    """The process-wide FantraxMCPClient, created on first use."""
    global _client
    if _client is None:
        _client = FantraxMCPClient()
    return _client
