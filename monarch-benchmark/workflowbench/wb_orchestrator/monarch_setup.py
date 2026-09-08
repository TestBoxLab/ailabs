"""`wb monarch setup`: prepare one product's knowledge base inside Monarch, once.

Five steps, printed one line each (contracts/cli.md):

  generate  write the seed folders from the product's OpenAPI documents, then
            run Monarch's own `validate-seeds.mjs` when `MONARCH_SEED_VALIDATOR`
            names it (unset: skipped silently)
  conform   every action of the product's services is executed against the
            simulated apps; a read whose declared response is false stops the
            command before anything is imported (feature 008)
  mounted   the discovery service must already see them on disk
  import    one knowledge-base import per app, hashes recorded; it also
            creates the product, so the bench never registers one itself
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
TIMEOUT_S = 60.0   # the 686-file import against the fake has timed out at 30 under load
_VAR = re.compile(r"\$\{(\w+)\}")


class Stop(Exception):
    def __init__(self, code: int, step: str, message: str):
        self.code, self.step, self.message = code, step, message
        super().__init__(f"{step}: {message}")


def expand(value: str | None, env: dict, field: str) -> str:
    """Replace ${NAME} with env[NAME]; an unset variable stops the command."""
    if not value:
        raise Stop(4, "config", f"{field} is not set in the harness file")

    def sub(m):
        name = m.group(1)
        if not env.get(name):
            raise Stop(4, "config", f"{field}: environment variable {name} is not set")
        return env[name]

    return _VAR.sub(sub, value).rstrip("/")

def public_front_door_url(harness, env) -> str:
    """The address Monarch's containers use to reach the front door: the harness's
    `shim_public_url` (a tunnel such as ngrok; `${VAR}` expanded) when set, else
    `http://<shim_public_host>:<shim_port>` for Monarch in Docker on this machine."""
    if harness.shim_public_url:
        return expand(harness.shim_public_url, env, "shim_public_url").rstrip("/")
    return f"http://{harness.shim_public_host}:{harness.shim_port}"



def fd_headers(harness, env: dict) -> dict:
    """The discovery service's gate header, when the harness names the variable.

    The Railway deployment has `x-fd-api-key` on for every /v1/* route (verified
    4 Sep 2026); a local one has no gate, so the field and the variable are both
    optional and an unset variable simply sends nothing.
    """
    key = env.get(getattr(harness, "fd_api_key_env", None) or "")
    return {"x-fd-api-key": key} if key else {}


def _get(url: str, step: str, timeout: float = TIMEOUT_S, headers: dict | None = None):
    """GET JSON; any transport or decoding failure stops the command naming `step`."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as e:
        raise Stop(4, step, f"discovery service unreachable at {url}: {e}") from e


def _post(url: str, payload: dict, step: str, timeout: float = TIMEOUT_S,
          headers: dict | None = None):
    """POST JSON; any transport or decoding failure stops the command naming `step`."""
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          **(headers or {})}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as e:
        raise Stop(4, step, f"{url} failed: {e}") from e


def run(product_path, harness_path, out_dir, env: dict, stdout,
        conform: bool = True) -> int:
    def say(mark: str, step: str, detail: str = "") -> None:
        print(f"[{mark}] {step}{': ' + detail if detail else ''}", file=stdout)

    out = Path(out_dir).resolve()
    try:
        product = config.load_product(product_path)
        harness = config.load_harness(harness_path)
        fd_url = expand(harness.fd_url, env, "fd_url")
        shim_public_url = public_front_door_url(harness, env)
        fd_head = fd_headers(harness, env)

        # 1. generate
        try:
            summary = seeds.generate(out, shim_public_url)
        except seeds.SeedGap as e:
            for g in e.gaps:
                print(f"      {g.file}: {g.gap}", file=stdout)
            raise Stop(2, "generate", f"{len(e.gaps)} gap(s); nothing written") from e
        say("ok", "generate", f"operations_in_spec={summary.operations_in_spec} "
                              f"files_written={summary.files_written} folders={len(summary.folders)}")
        _run_seed_validator(out, env, stdout)
        if conform:
            _conform_gate(out, product.services, stdout)

        # 2. mounted
        want = sorted(seeds.product_slug(s) for s in product.services)
        listed = {s["slug"] for s in _get(f"{fd_url}/v1/seeds", "mounted", headers=fd_head).get("items", [])}
        missing = [s for s in want if s not in listed]
        if missing:
            say("stop", "mounted", f"{len(missing)} of {len(want)} seed folders are not visible "
                                   f"to the discovery service (first: {missing[0]})")
            print(_override_snippet(out), file=stdout)
            return 3
        say("ok", "mounted", f"{len(want)} seed folders visible")

        # 3. import (also creates the product: a separate POST /v1/products
        # registered a second, slugified product per app -- verified 4 Sep 2026)
        kb: dict[str, str] = {}
        for slug in want:
            res = _post(f"{fd_url}/v1/seeds/{slug}/import", {}, f"import {slug}",
                        headers=fd_head)
            kb[slug] = str((res.get("after") or {}).get("kb_hash") or "")
            print(f"      {slug}: actions_imported={res.get('actions_imported')} "
                  f"kb_hash={kb[slug][:12]}", file=stdout)
        say("ok", "import", f"{len(kb)} apps")

        # 5. granted
        # ponytail: static warning, not a check; Monarch names no grant route yet
        # (open question 2). Upgrade: query the org's products and print the missing slugs.
        say("warn", "granted", "unknown (open question 2): verify the 47 bench-* products "
                               "are granted to the bench user's organisation")

        # 6. write
        path, changed = _write_kb(Path(product_path), product.name, shim_public_url, kb)
        say("ok", "write", f"{path} ({'changed' if changed else 'unchanged'})")
        return 0
    except Stop as stop:
        say("stop", stop.step, stop.message)
        return stop.code


def _run_seed_validator(out: Path, env: dict, stdout) -> None:
    """Monarch's own seed validator, when the environment names it.

    `MONARCH_SEED_VALIDATOR` points at `validate-seeds.mjs` in the Monarch
    checkout. It is the authority on what the FD import accepts and what the
    engine executes, so a non-zero exit stops the command before anything is
    imported. Unset -- the usual case, and every CI box without the Monarch
    checkout -- skips silently.
    """
    import shutil
    import subprocess

    script = (env.get("MONARCH_SEED_VALIDATOR") or "").strip()
    if not script:
        return
    node = shutil.which("node")
    if not node:
        raise Stop(2, "generate", "MONARCH_SEED_VALIDATOR is set but `node` is not on PATH")
    if not Path(script).is_file():
        raise Stop(2, "generate", f"MONARCH_SEED_VALIDATOR does not name a file: {script}")
    # A node process that dies on a Windows structured exception (0xC0000000+)
    # never reached the seeds, so its exit code says nothing about them; retry
    # once rather than stop a good run on a crashed child (seen once under the
    # test suite's fake servers, 4 Sep 2026).
    for attempt in (1, 2):
        try:
            done = subprocess.run([node, script, str(out), "--no-warn"],
                                  capture_output=True, text=True, timeout=TIMEOUT_S)
        except (OSError, subprocess.SubprocessError) as e:
            raise Stop(2, "generate", f"seed validator failed to run: {e}") from e
        if not (done.returncode > 0xC0000000 and attempt == 1):
            break
    output = (done.stdout or "") + (done.stderr or "")
    for line in output.splitlines():
        print(f"      {line}", file=stdout)
    if done.returncode != 0:
        raise Stop(2, "generate",
                   f"seed validator reported errors (exit {done.returncode})")
    print("[ok] validate: seed validator reported no errors", file=stdout)


def _conform_gate(out: Path, services: list[str], stdout) -> None:
    """Feature 008: is every action of this product's services TRUE?

    A read or list whose declared response is not the response the front door
    really returns is what broke Google Sheets, so it stops the command before
    anything is imported. A failing write only warns: a write needs inputs the
    check cannot always invent.
    """
    from wb_world import conformance

    corpus = conformance.default_corpus_dirs()
    if not corpus:
        return                                   # no corpus, no worlds to check against
    report = conformance.check(out, corpus, list(services))
    report.write_json(out.parent / "monarch-conformance.json")   # outside the seed folder: the deploy script scans it
    bad_reads = [r for r in report.rows if r.is_read and r.verdict in
                 ("schema_mismatch", "extract_empty", "request_rejected")]
    no_handler = [r for r in report.rows if r.verdict == "no_handler"]
    if no_handler:
        print(f"[warn] conform: {len(no_handler)} action(s) name a route the simulated "
              f"app does not serve (first: {no_handler[0].action_id})", file=stdout)
    bad_writes = [r for r in report.rows if not r.is_read and r.verdict not in
                  conformance.BENIGN]
    if bad_writes:
        print(f"[warn] conform: {len(bad_writes)} write action(s) did not check out "
              f"(first: {bad_writes[0].action_id} {bad_writes[0].verdict})", file=stdout)
    if bad_reads:
        for r in bad_reads[:5]:
            print(f"      {r.action_id}: {r.verdict}: {r.detail[:110]}", file=stdout)
        raise Stop(2, "conform",
                   f"{len(bad_reads)} read action(s) do not match the simulated apps; "
                   f"nothing imported (see {out.parent / 'monarch-conformance.json'})")
    print(f"[ok] conform: {len(report.rows)} actions true against the simulated apps",
          file=stdout)


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
