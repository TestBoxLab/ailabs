"""wb-world: the MCP server bare arms talk to.

One episode per server process. Configuration via env:
  WB_TASK_FILE      path to the task json (required)
  WB_EPISODE_ID     episode id (required)
  WB_SNAPSHOT_DIR   where snapshot0/snapshot1 land (required)
  WB_FROZEN_TIME    optional ISO timestamp for the world clock

Exposes exactly three tools — api_search, api_fetch, base64_encode — the same
surface every arm gets (parity by construction; see T0 spec, Deliverable 1).
Snapshot0 is written at startup; snapshot1 at process exit, so the out-of-process
grader never depends on the agent behaving well.
"""
from __future__ import annotations

import atexit
import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from wb_world.episode import Episode, load_task_file

mcp = FastMCP("wb-world")
_episode: Episode | None = None


def _get_episode() -> Episode:
    global _episode
    if _episode is None:
        task = load_task_file(os.environ["WB_TASK_FILE"])
        _episode = Episode(
            task,
            episode_id=os.environ["WB_EPISODE_ID"],
            frozen_time=os.environ.get("WB_FROZEN_TIME"),
        )
        snap_dir = Path(os.environ["WB_SNAPSHOT_DIR"])
        snap_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / "snapshot0.json").write_text(json.dumps(_episode.snapshot0))
        atexit.register(_write_final, snap_dir)
    return _episode


def _write_final(snap_dir: Path) -> None:
    if _episode is not None:
        (snap_dir / "snapshot1.json").write_text(json.dumps(_episode.finish()))
        (snap_dir / "tool_calls.json").write_text(json.dumps(_episode.tool_calls))


@mcp.tool()
def api_search(query: str, top_k: int = 5) -> str:
    """Search available API endpoints by keyword. Use before api_fetch.

    Returns JSON with matching endpoints: id, method, url, description,
    parameters, request body, and response format."""
    return _get_episode().api_search(query, top_k)


@mcp.tool()
def api_fetch(method: str, url: str,
              params: str | dict | None = None, body: str | dict | None = None) -> str:
    """Call an API endpoint by its full URL (from api_search results).

    method: GET/POST/PUT/PATCH/DELETE. params/body: JSON strings or objects.
    (Both forms accepted: FastMCP parses JSON-looking strings into objects.)"""
    if isinstance(params, dict):
        params = json.dumps(params)
    if isinstance(body, dict):
        body = json.dumps(body)
    return _get_episode().api_fetch(method, url, params=params, body=body)


@mcp.tool()
def base64_encode(text: str) -> str:
    """Encode text to base64url (required by Gmail API body fields)."""
    return _get_episode().base64_encode(text)


def main() -> None:
    _get_episode()  # seed + snapshot0 before serving
    mcp.run()


if __name__ == "__main__":
    main()
