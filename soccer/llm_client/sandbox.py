"""
Parent side of the run_python tool: runs a short analysis script in a separate, restricted
Python process (sandbox_harness.py) and relays the script's tool() calls to the fantrax_mcp
server, so the script can pull league data without it passing through the model's context.

See sandbox_harness.py for what the script can and can't do.
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Iterable

HARNESS = Path(__file__).resolve().parent / "sandbox_harness.py"
WALL_SECONDS = 90
# No secrets reach the child. One BLAS thread keeps numpy's startup memory small.
CHILD_ENV = {"PATH": "/usr/bin:/bin", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}


def run_script(code: str, call_tool: Callable[[str, Dict[str, Any]], Any], allowed_tools: Iterable[str]) -> Dict[str, Any]:
    """Runs `code` and returns {"output": str, "error": str | None}.

    Args:
        code: The script. tool(name, **args) inside it calls call_tool(name, args).
        call_tool: Runs one data tool and returns its JSON-serializable result.
        allowed_tools: Tool names the script may call.
    """
    allowed = set(allowed_tools)
    with tempfile.TemporaryDirectory(prefix="commish-py-") as workdir:
        proc = subprocess.Popen(
            [sys.executable, "-I", "-B", str(HARNESS)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=workdir, env=CHILD_ENV,
        )
        timed_out = threading.Event()

        def stop():
            timed_out.set()
            proc.kill()

        timer = threading.Timer(WALL_SECONDS, stop)
        timer.start()
        try:
            proc.stdin.write(json.dumps({"code": code}) + "\n")
            proc.stdin.flush()
            for line in proc.stdout:
                message = json.loads(line)
                if message.get("type") == "done":
                    return {"output": message["output"], "error": message["error"]}
                name = message.get("name")
                if name in allowed:
                    result = call_tool(name, message.get("args") or {})
                else:
                    result = {"error": f'tool("{name}") isn\'t available. Available: {", ".join(sorted(allowed))}'}
                proc.stdin.write(json.dumps(result, default=str) + "\n")
                proc.stdin.flush()
        except (BrokenPipeError, ValueError):
            pass
        finally:
            timer.cancel()
            proc.kill()
            stderr = proc.stderr.read()
            proc.wait()
        if timed_out.is_set():
            return {"output": "", "error": f"The script was stopped after {WALL_SECONDS} seconds."}
        if proc.returncode == -signal.SIGXCPU:
            return {"output": "", "error": "The script was stopped: it used too much CPU time."}
        return {"output": "", "error": f"The script crashed: {stderr.strip()[-1500:] or 'no output'}"}
