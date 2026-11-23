"""Small stdio MCP adapter for the versioned SU2 Airfoil Studio backend API.

Protocol logging is never written to stdout. This adapter intentionally exposes
the versioned operations implemented by portable_api.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import portable_api

VERSION = "2025-11-25"
TOOLS = [
    {"name": "studio_info", "description": "Inspect backend paths, supported modes, and SU2 discovery.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "studio_schema", "description": "List validated numerical parameters and defaults.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "studio_run", "description": "Generate a mesh, run SU2 CFD, produce a report, or optimize a converged CFD case. The output directory must be new for mesh, solve, and optimize.",
     "inputSchema": {"type": "object", "properties": {"mode": {"type": "string", "enum": ["mesh", "solve", "report", "optimize"]},
         "airfoil": {"type": "string"}, "output_dir": {"type": "string"},
         "parameters": {"type": "object"}, "case_dir": {"type": "string"},
         "method": {"type": "string", "enum": ["cst", "bce", "hybrid", "relay"]},
         "steps": {"type": "integer", "minimum": 1, "maximum": 100}},
         "required": ["mode", "output_dir"], "additionalProperties": False}},
]


def dispatch(message: dict) -> dict | None:
    method = message.get("method")
    if "id" not in message:
        return None
    identifier = message["id"]
    try:
        if method == "initialize":
            result = {"protocolVersion": VERSION, "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "su2-airfoil-studio", "version": "0.1.0"}}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = message.get("params") or {}
            name, args = params.get("name"), params.get("arguments") or {}
            if not isinstance(args, dict):
                raise ValueError("Tool arguments must be an object.")
            if name == "studio_info":
                output = portable_api.info()
            elif name == "studio_schema":
                output = {"api_version": portable_api.API_VERSION, "parameters": portable_api.schema()}
            elif name == "studio_run":
                output, _ = portable_api.execute(args)
            else:
                raise ValueError(f"Unknown tool: {name}")
            result = {"content": [{"type": "text", "text": json.dumps(output, ensure_ascii=False)}],
                      "structuredContent": output, "isError": not output.get("ok", True)}
        else:
            return {"jsonrpc": "2.0", "id": identifier,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}}
        return {"jsonrpc": "2.0", "id": identifier, "result": result}
    except Exception as exc:
        if method == "tools/call":
            return {"jsonrpc": "2.0", "id": identifier, "result": {"content": [
                {"type": "text", "text": str(exc)}], "isError": True}}
        return {"jsonrpc": "2.0", "id": identifier,
                "error": {"code": -32603, "message": str(exc)}}


def main() -> None:
    for line in sys.stdin:
        try:
            response = dispatch(json.loads(line))
            if response is not None:
                print(json.dumps(response, ensure_ascii=False, allow_nan=False), flush=True)
        except Exception as exc:
            print(f"MCP input error: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
