"""`wb monarch setup`: prepare one product's knowledge base inside Monarch, once.

Six steps, printed one line each (contracts/cli.md):

  generate  write the seed folders from the product's OpenAPI documents
  mounted   the discovery service must already see them on disk
  register  one product per simulated app
  import    one knowledge-base import per app, hashes recorded
  granted   an open question; warned about, never fails
  write     config/products/<product>.monarch-kb.yaml, the file `wb run` checks

Spends no model money: it talks only to the discovery service, never to the
Monarch backend or Langfuse. Idempotent: a second run writes the same bytes.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

from wb_orchestrator import config
from wb_world import seeds

# The path inside the discovery-service container that its seed catalogue scans.
# ponytail: taken from seed-catalog.ts; verify against the running image at T053 (live gate).
FIXTURES_MOUNT_PATH = "/app/api/src/seeds/fixtures/public-api-seeds/bench-mounted"
SEEDS_FORMAT = "public-api-seeds@1"
TIMEOUT_S = 30.0
_VAR = re.compile(r"\$\{(\w+)\}")


class _Stop(Exception):
    def __init__(self, code: int, step: str, message: str):
        self.code, self.step, self.message = code, step, message
        super().__init__(f"{step}: {message}")


def _expand(value: str | None, env: dict, field: str) -> str:
    """Replace ${NAME} with env[NAME]; an unset variable stops the command."""
    if not value:
        raise _Stop(4, "config", f"{field} is not set in the harness file")

    def sub(m):
        name = m.group(1)
        if not env.get(name):
            raise _Stop(4, "config", f"{field}: environment variable {name} is not set")
        return env[name]

    return _VAR.sub(sub, value).rstrip("/")


def _get(url: str, step: str, timeout: float = TIMEOUT_S):
    """GET JSON; any transport or decoding failure stops the command naming `step`."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as e:
        raise _Stop(4, step, f"discovery service unreachable at {url}: {e}") from e


def _post(url: str, payload: dict, step: str, timeout: float = TIMEOUT_S):
    """POST JSON; any transport or decoding failure stops the command naming `step`."""
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as e:
        raise _Stop(4, step, f"{url} failed: {e}") from e


def _display_name(service: str) -> str:
    return f"{service.replace('_', ' ').title()} (benchmark)"


def run(product_path, harness_path, out_dir, env: dict, stdout) -> int:
    def say(mark: str, step: str, detail: str = "") -> None:
        print(f"[{mark}] {step}{': ' + detail if detail else ''}", file=stdout)

    out = Path(out_dir).resolve()
    try:
        product = config.load_product(product_path)
        harness = config.load_harness(harness_path)
        fd_url = _expand(harness.fd_url, env, "fd_url")
        shim_public_url = f"http://{harness.shim_public_host}:{harness.shim_port}"

        # 1. generate
        try:
            summary = seeds.generate(out, shim_public_url)
        except seeds.SeedGap as e:
            for g in e.gaps:
                print(f"      {g.file}: {g.gap}", file=stdout)
            raise _Stop(2, "generate", f"{len(e.gaps)} gap(s); nothing written") from e
        say("ok", "generate", f"operations_in_spec={summary.operations_in_spec} "
                              f"files_written={summary.files_written} folders={len(summary.folders)}")

        # 2. mounted
        want = sorted(f"bench-{s}" for s in product.services)
        listed = {s["slug"] for s in _get(f"{fd_url}/v1/seeds", "mounted").get("items", [])}
        missing = [s for s in want if s not in listed]
        if missing:
            say("stop", "mounted", f"{len(missing)} of {len(want)} seed folders are not visible "
                                   f"to the discovery service (first: {missing[0]})")
            print(_override_snippet(out), file=stdout)
            return 3
        say("ok", "mounted", f"{len(want)} seed folders visible")

        # 3. register
        for slug in want:
            _post(f"{fd_url}/v1/products",
                  {"slug": slug, "display_name": _display_name(slug.removeprefix("bench-"))},
                  f"register {slug}")
        say("ok", "register", f"{len(want)} products")

        # 4. import
        kb: dict[str, str] = {}
        for slug in want:
            res = _post(f"{fd_url}/v1/seeds/{slug}/import", {}, f"import {slug}")
            kb[slug] = str((res.get("after") or {}).get("kb_hash") or "")
            print(f"      {slug}: actions_imported={res.get('actions_imported')} "
                  f"kb_hash={kb[slug][:12]}", file=stdout)
        say("ok", "import", f"{len(kb)} apps")

        # 5. granted
        say("warn", "granted", "unknown (open question 2): verify the 47 bench-* products "
                               "are granted to the bench user's organisation")

        # 6. write
        path, changed = _write_kb(Path(product_path), product.name, shim_public_url, kb)
        say("ok", "write", f"{path} ({'changed' if changed else 'unchanged'})")
        return 0
    except _Stop as stop:
        say("stop", stop.step, stop.message)
        return stop.code


def _override_snippet(out: Path) -> str:
    return ("\n"
            "services:\n"
            "  fdapi:\n"
            "    volumes:\n"
            f"      - {out}:{FIXTURES_MOUNT_PATH}:ro\n"
            "\n"
            "add this to monarch-enterprise/docker-compose.override.yaml, restart the "
            "discovery service, then rerun wb monarch setup")


def _write_kb(product_path: Path, name: str, shim_public_url: str,
              kb: dict[str, str]) -> tuple[Path, bool]:
    path = product_path.with_name(f"{name}.monarch-kb.yaml")
    doc = {"product": name, "generated_at": "", "seeds_format": SEEDS_FORMAT,
           "shim_public_url": shim_public_url, "kb": dict(sorted(kb.items()))}
    old = {}
    if path.is_file():
        old = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    same = old.get("kb") == doc["kb"] and old.get("shim_public_url") == shim_public_url
    doc["generated_at"] = str(old.get("generated_at")) if same else \
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    text = yaml.safe_dump(doc, sort_keys=True, default_flow_style=False)
    changed = not path.is_file() or path.read_text(encoding="utf-8") != text
    if changed:
        path.write_text(text, encoding="utf-8")
    return path, changed
