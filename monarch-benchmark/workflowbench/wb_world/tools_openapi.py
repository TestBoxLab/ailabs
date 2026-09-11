"""Publish a world's tool list as an OpenAPI document (feature 026, research.md R4).

Monarch's discovery step reads operations, parameters and descriptions. A world whose
surface is tools rather than REST resources -- EnterpriseOps-Gym's 512 MCP tools,
tau2's Python functions -- still has to present that surface as a document, or it
cannot be mapped and Monarch cannot compete on it.

The rule is deliberately dull: one tool, one operation, `POST /{service}/{tool_name}`,
the tool's own input schema as the request body, its real name as the operation id.
Nothing is invented. Guessing that `create_incident` is really `POST /incidents`
would describe an interface the world does not have, and the first agent to follow
that guess would get a 404 it could not diagnose.
"""
from __future__ import annotations

from typing import Any

#: The keys a tool description may use for its input schema, in the order tried.
#: MCP says `inputSchema`; most other sources say one of the rest.
_SCHEMA_KEYS = ("inputSchema", "input_schema", "parameters", "schema")

_EMPTY_OBJECT: dict[str, Any] = {"type": "object", "properties": {}}


def tool_schema(tool: dict[str, Any]) -> dict[str, Any]:
    for key in _SCHEMA_KEYS:
        value = tool.get(key)
        if isinstance(value, dict):
            return value
    return dict(_EMPTY_OBJECT)


def build_tool_spec(service: str, tools: list[dict[str, Any]], server_url: str) -> dict[str, Any]:
    """One OpenAPI 3.1 document for one service's tools."""
    paths: dict[str, Any] = {}
    for tool in tools:
        name = tool["name"]
        paths[f"/{service}/{name}"] = {
            "post": {
                "operationId": name,
                "summary": (tool.get("description") or name).strip().splitlines()[0][:120],
                "description": tool.get("description") or name,
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": tool_schema(tool)}},
                },
                "responses": {
                    "200": {
                        "description": "the tool's result",
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    }
                },
            }
        }
    return {
        "openapi": "3.1.0",
        "info": {"title": service, "version": "1.0.0"},
        "servers": [{"url": server_url}],
        "paths": paths,
    }
