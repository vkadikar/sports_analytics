"""
Child-process side of run_python (see sandbox.py). Runs as `python -I -B sandbox_harness.py`.

Protocol over stdin/stdout, one JSON object per line:
    parent -> child   {"code": str}                     the script to run
    child  -> parent  {"type": "tool", "name", "args"}  the script called tool(); parent replies
    parent -> child   <tool result JSON>                 with the result on the next line
    child  -> parent  {"type": "done", "output", "error"}

The script gets pandas (pd), numpy (np), a few pure stdlib modules, and tool(). This is a
restricted environment, not a hardened sandbox:
  - The code is checked before it runs: no underscore attributes or names, no file/eval/
    introspection builtins, no file-reading or file-writing library functions, and imports
    only from ALLOWED_MODULES.
  - Modules are handed over as namespaces with their submodules removed, so the script can't
    reach os or sys through them (e.g. statistics.sys).
  - After the imports, resource limits cap CPU time, block new processes, and block writing
    files. The parent also passes an empty environment (no secrets) and a wall-clock timeout.
"""

import ast
import builtins
import contextlib
import io
import json
import re
import sys
import traceback
import types

import bisect
import collections
import datetime
import decimal
import fractions
import functools
import heapq
import itertools
import math
import random
import statistics

import numpy
import pandas

CPU_SECONDS = 10
MAX_TOOL_CALLS = 40
MAX_OUTPUT_CHARS = 12000

# Attributes a script may not touch: file I/O, code evaluation, introspection, and the frame and
# code objects that lead back to real builtins (generator.gi_frame.f_globals).
BANNED_NAMES = {
    "open", "exec", "eval", "compile", "getattr", "setattr", "delattr", "globals", "locals",
    "vars", "input", "breakpoint", "help", "memoryview", "exit", "quit", "dir",
    "attrgetter", "methodcaller", "query", "os", "sys", "modules", "builtins", "subprocess",
    "importlib", "shutil", "socket", "ctypes", "pathlib", "io", "compat", "lib", "testing",
    "system", "popen", "environ", "getenv", "mro", "DataSource", "ExcelWriter", "HDFStore",
    "memmap", "fromfile", "tofile", "genfromtxt", "fromregex", "ctypeslib",
    "load", "loads", "loadtxt", "save", "savez", "savez_compressed", "savetxt",
    "f_globals", "f_locals", "f_builtins", "f_back", "f_code", "gi_frame", "gi_code",
    "cr_frame", "cr_code", "ag_frame", "ag_code", "tb_frame", "tb_next", "co_code", "co_consts",
}
# read_csv, to_parquet, ...: pandas' file readers and writers.
BANNED_PATTERN = re.compile(
    r"^(read_\w+|to_(csv|json|excel|parquet|pickle|sql|feather|hdf|html|xml|stata|clipboard|latex|orc))$"
)


def _banned(name: str) -> bool:
    return name.startswith("_") or name in BANNED_NAMES or bool(BANNED_PATTERN.match(name))


def _namespace(module, submodules=()):
    """A module's public, non-module attributes (plus the named submodules, recursively)."""
    attrs = {}
    for name in dir(module):
        if _banned(name):
            continue
        try:
            value = getattr(module, name)
        except Exception:
            continue
        if isinstance(value, types.ModuleType):
            if name in submodules:
                attrs[name] = _namespace(value)
            continue
        attrs[name] = value
    return types.SimpleNamespace(**attrs)


pandas.set_option("display.width", 140)
pandas.set_option("display.max_columns", 30)
pandas.set_option("display.max_rows", 80)

ALLOWED_MODULES = {
    "pandas": _namespace(pandas),
    "numpy": _namespace(numpy, submodules=("linalg", "random", "fft")),
    **{m.__name__: _namespace(m) for m in (
        bisect, collections, datetime, decimal, fractions, functools, heapq, itertools, math,
        random, statistics, re, json,
    )},
}


def _import(name, globals=None, locals=None, fromlist=(), level=0):
    parts = name.split(".")
    if level or parts[0] not in ALLOWED_MODULES:
        raise ImportError(f"Only these modules can be imported: {', '.join(sorted(ALLOWED_MODULES))}")
    module = ALLOWED_MODULES[parts[0]]
    if not fromlist:
        return module
    for part in parts[1:]:
        module = getattr(module, part)
    return module


SAFE_BUILTINS = {k: v for k, v in vars(builtins).items() if not _banned(k)}
SAFE_BUILTINS["__import__"] = _import
SAFE_BUILTINS["__build_class__"] = builtins.__build_class__


def _check(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and _banned(node.attr):
            raise ValueError(f'Attribute "{node.attr}" isn\'t allowed.')
        # Banned builtins are simply missing from SAFE_BUILTINS, so plain names only need the dunder
        # check (e.g. __builtins__); variables like "saves" or "f_scores" are fine.
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError(f'Name "{node.id}" isn\'t allowed.')
        if isinstance(node, ast.alias) and _banned(node.name.split(".")[-1]) and node.name not in ALLOWED_MODULES:
            raise ValueError(f'Importing "{node.name}" isn\'t allowed.')


def _limit_resources() -> None:
    try:
        import resource
    except ImportError:
        return
    used = int(resource.getrusage(resource.RUSAGE_SELF).ru_utime) + 1
    for limit, value in (
        (resource.RLIMIT_CPU, used + CPU_SECONDS),
        (resource.RLIMIT_NPROC, 0),
        (resource.RLIMIT_FSIZE, 0),
    ):
        try:
            resource.setrlimit(limit, (value, value))
        except (ValueError, OSError):
            pass


def main() -> None:
    proto_in, proto_out = sys.stdin, sys.stdout

    def send(message):
        proto_out.write(json.dumps(message, default=str) + "\n")
        proto_out.flush()

    calls = 0

    def tool(name, **args):
        """Calls a league data tool and returns its result (a dict; {"error": ...} on failure)."""
        nonlocal calls
        calls += 1
        if calls > MAX_TOOL_CALLS:
            raise RuntimeError(f"More than {MAX_TOOL_CALLS} tool() calls in one script.")
        send({"type": "tool", "name": name, "args": args})
        return json.loads(proto_in.readline())

    code = json.loads(proto_in.readline())["code"]
    _limit_resources()

    buffer = io.StringIO()
    error = None
    try:
        tree = ast.parse(code, "<analysis>")
        _check(tree)
        # Like a notebook cell: if the last statement is an expression, show its value.
        last = tree.body.pop() if tree.body and isinstance(tree.body[-1], ast.Expr) else None
        scope = {
            "__builtins__": SAFE_BUILTINS, "__name__": "__analysis__",
            "pd": ALLOWED_MODULES["pandas"], "np": ALLOWED_MODULES["numpy"], "tool": tool,
        }
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            exec(compile(tree, "<analysis>", "exec"), scope)
            if last is not None:
                value = eval(compile(ast.Expression(last.value), "<analysis>", "eval"), scope)
                if value is not None:
                    print(repr(value) if not isinstance(value, (pandas.DataFrame, pandas.Series)) else value)
    except Exception:
        error = "".join(traceback.format_exc(limit=-3).splitlines(True)[-6:])

    output = buffer.getvalue()
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + f"\n... (output truncated at {MAX_OUTPUT_CHARS} characters)"
    send({"type": "done", "output": output, "error": error})


if __name__ == "__main__":
    main()
