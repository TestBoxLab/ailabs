"""Stock Monarch Enterprise as a Studio comparison version (feature 011, checkpoint 3).

The Studio drives the same competitor the CLI rounds use (`wb_arms/monarch.py`) and
watches it through the arm's observer hook, so the Activity lane shows the builder's
frames and every recipe node's state as the engine reports it.

Three honesty rules, enforced here rather than in the page:

* Nothing launches before a verification probe passes against the exact deployment
  the harness file names: liveness, health with a session, the knowledge base Monarch
  holds equals the frozen file, Langfuse answers, and the served build can be named
  from the checkout `monarch_repo` points at. The probe is stored beside the Studio's
  runs and expires.
* The version's name carries the build (`monarch@<sha>`, plus `+<branch>` off main,
  plus `*` when the checkout is dirty). A branch or a patch is a custom build and is
  labelled so; only a clean `main` may be called stock.
* Every attempt reserves a ceiling in the shared weekly ledger before Monarch is
  called and settles with the Langfuse total afterwards; an attempt whose cost could
  not be read keeps its hold and says so (`billing=unknown`).

The provider path (Bedrock in the stock product) is not observable from the bench:
the price table declares what the deployment is billed as, and the manifest records
that declaration as a declaration, never as a verified fact.
"""
from __future__ import annotations

import hashlib
import re
import json
import os
import subprocess
import urllib.error
import urllib.request
from urllib.parse import urlparse
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from wb_arms import runtime_manifest as rm
from wb_arms.api_loop import ArmResult, EpisodeTimeout, InfraError
from wb_arms.monarch import CEILING_ENV, DEFAULT_CEILING_USD, MonarchArm, attempt_ceiling_usd  # noqa: F401  (re-exported)
from wb_arms.monarch_client import MonarchClient
from wb_orchestrator import config
from wb_orchestrator.monarch_setup import Stop, expand, public_front_door_url
from wb_results.evidence import write_json
from wb_world.episode import EvidenceWriteError

from wb_orchestrator.monarch_probe import PROBE_TTL, load_probe, probe_path

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "default-monarch-enterprise"
PRODUCT = "simulated-apps"
HARNESS = "monarch"
ATTEMPT_TIMEOUT_S = 1800.0            # the tier plans' allowance per attempt
# DEFAULT_CEILING_USD, CEILING_ENV and attempt_ceiling_usd live with the arm
# (wb_arms.monarch) since milestone M3, so the CLI reserves the same amount.
ENTERPRISE_REPOSITORY = "https://github.com/TestBoxLab/monarch"
ENTERPRISE_DIRECTORY = "monarch-enterprise"

_now = lambda: datetime.now(timezone.utc)  # noqa: E731


# -- configuration ---------------------------------------------------------------

def config_dir(studio) -> Path:
    return Path(getattr(studio, "enterprise_config_dir", None) or ROOT / "config")


def environment(studio) -> dict:
    env = getattr(studio, "enterprise_env", None)
    if env is not None:
        return env
    load = getattr(studio, "_load_env", None)
    if load is not None:
        load()
    return dict(os.environ)


class Setup:
    """Everything the competitor needs, loaded from the config tree; or the reasons it cannot be."""

    def __init__(self, studio):
        self.config_dir = config_dir(studio)
        self.env = environment(studio)
        self.problems: list[str] = []
        self.harness = self.product = self.kb = self.price_table = None
        self.product_name = getattr(studio, "enterprise_product", PRODUCT)
        self.harness_name = getattr(studio, "enterprise_harness", HARNESS)
        self.kb_path = self.config_dir / "products" / f"{self.product_name}.monarch-kb.yaml"
        self.version: str | None = None
        self.checkout: dict | None = None
        self._load()

    def _load(self) -> None:
        harness_path = self.config_dir / "harnesses" / f"{self.harness_name}.yaml"
        try:
            self.harness = config.load_harness(harness_path)
            if self.harness.kind != "monarch":
                raise config.ConfigError(harness_path, "kind", "must be monarch")
            if not self.harness.runnable:
                raise config.ConfigError(harness_path, "runnable", "the Monarch harness is marked not runnable")
            if "create-run" not in (self.harness.modes or []):
                raise config.ConfigError(harness_path, "modes", "create-run is not among the harness modes")
        except (config.ConfigError, OSError, ValueError) as exc:
            self.problems.append(f"Harness file: {exc}")
        try:
            self.product = config.load_product(self.config_dir / "products" / f"{self.product_name}.yaml")
        except (config.ConfigError, OSError, ValueError) as exc:
            self.problems.append(f"Product file: {exc}")
        if self.product is not None:
            try:
                self.kb = config.load_monarch_kb(self.kb_path, self.product)
            except (config.ConfigError, OSError, ValueError) as exc:
                self.problems.append(f"Knowledge base: {exc}; run `wb monarch setup` against this deployment")
        if self.harness is not None:
            table = self.harness.price_table
            path = self.config_dir / "models" / f"{table}.yaml" if table else None
            try:
                if path is None or not path.is_file():
                    raise ValueError(f"the harness names no price table file ({table!r})")
                self.price_table = config.load_price_table(path)
            except (config.ConfigError, OSError, ValueError) as exc:
                self.problems.append(f"Price table: {exc}")
            for field in ("base_url", "fd_url", "langfuse_url"):
                try:
                    expand(getattr(self.harness, field), self.env, field)
                except Stop as stop:
                    self.problems.append(f"Environment: {stop.message}")
            if not (self.env.get(self.harness.credential_env or "") or self.env.get(self.harness.login_password_env or "")):
                self.problems.append(f"Environment: neither {self.harness.credential_env} nor {self.harness.login_password_env} is set")
            for key in (self.harness.langfuse_public_key_env, self.harness.langfuse_secret_key_env):
                if key and not self.env.get(key):
                    self.problems.append(f"Environment: {key} is not set (Monarch's cost is read from Langfuse)")
            try:
                attempt_ceiling_usd(self.env)
            except ValueError as exc:
                self.problems.append(f"Environment: {exc}")
            if not self.harness.monarch_repo:
                self.problems.append("Build: the harness names no `monarch_repo`; the served build cannot be named")
            else:
                repo = config.from_workflowbench(self.harness.monarch_repo, self.config_dir)
                try:
                    self.checkout = checkout_identity(repo)
                    self.version = self.checkout["version"]
                except ValueError as exc:
                    declared = (self.env.get("MONARCH_BUILD") or "").strip()
                    if declared:
                        # A hosted Studio has no checkout: the operator declares the served build
                        # (for example `monarch@2ede4b3e+feat/railway-dev-deploy`) and, when known,
                        # its full commit (MONARCH_BUILD_COMMIT). Declared is never stock.
                        commit = (self.env.get("MONARCH_BUILD_COMMIT") or "").strip().lower() or None
                        if commit is not None and not re.fullmatch(r"[0-9a-f]{40}", commit):
                            self.problems.append(f"Build: MONARCH_BUILD_COMMIT must be a full 40-hex commit, not {commit!r}")
                            commit = None
                        self.checkout = {"commit": commit, "branch": None, "dirty": None, "patch_sha256": None,
                                         "version": declared, "declared": True, "reason": str(exc)}
                        self.version = declared
                    else:
                        self.problems.append(f"Build: cannot name the served build from {repo}: {exc}")

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def stock(self) -> bool:
        return (bool(self.checkout) and not self.checkout.get("declared")
                and self.checkout["branch"] == "main" and not self.checkout["dirty"])

    def ceiling(self) -> Decimal:
        return attempt_ceiling_usd(self.env)

    def arm(self) -> MonarchArm:
        if not self.ok:
            raise ValueError("Monarch Enterprise is not configured: " + "; ".join(self.problems))
        return MonarchArm(harness=self.harness, timeout_s=ATTEMPT_TIMEOUT_S, price_table=self.price_table,
                          kb=self.kb, env=self.env, name=self.version, mode="create-run", kb_path=self.kb_path)


def checkout_identity(repo: Path) -> dict:
    """Full commit, branch, a hash of any uncommitted change, and the build's name.

    The name follows `wb_arms.monarch.monarch_version` (`monarch@<sha>`,
    `+<branch>` off main) and adds `*` for a dirty tree, so a Studio row and a
    CLI row of the same checkout read the same. One pipe per git call: two
    pipes make `subprocess` spawn reader threads, which a Studio test that
    stubs `threading.Thread` cannot serve.
    """
    def git(*args: str) -> str:
        try:
            out = subprocess.run(["git", "-C", str(repo), *args], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True)
        except OSError as exc:  # no git binary on this host (the hosted Studio), or an unreadable path
            raise ValueError(f"git is not available here ({exc}); set MONARCH_BUILD to declare the served build") from exc
        if out.returncode != 0:
            raise ValueError(f"git {' '.join(args)}: {out.stdout.strip()}")
        return out.stdout
    commit = git("rev-parse", "HEAD").strip()
    short = git("rev-parse", "--short", "HEAD").strip()
    branch = git("rev-parse", "--abbrev-ref", "HEAD").strip()
    dirty = bool(git("status", "--porcelain").strip())
    patch = hashlib.sha256(git("diff", "HEAD").encode("utf-8", "replace")).hexdigest() if dirty else None
    version = f"monarch@{short}" + ("" if branch == "main" else f"+{branch}") + ("*" if dirty else "")
    return {"commit": commit, "branch": branch, "dirty": dirty, "patch_sha256": patch, "version": version}


# -- verification probe (probe_path and load_probe imported from wb_orchestrator.monarch_probe) ---



def verify(studio) -> dict:
    """Run every check against the deployment the harness names, store and return the record.

    Nothing here costs model money: no authoring run is started. The knowledge
    base check is the arm's own `prepare()`, the one the CLI runs before a round.
    """
    setup = Setup(studio)
    checks: list[dict] = [{"name": "configuration", "ok": setup.ok,
                           "detail": "harness, product, knowledge base, price table and environment" if setup.ok else "; ".join(setup.problems)}]
    record = {"checked_at": _now().isoformat(), "identity": IDENTITY, "version": setup.version,
              "checkout": setup.checkout, "stock": setup.stock, "checks": checks, "ok": False}
    if setup.ok:
        h, env = setup.harness, setup.env
        from wb_orchestrator.monarch_probe import harness_hash
        record["harness_sha256"] = harness_hash(h)
        record["product"] = setup.product.name
        base = expand(h.base_url, env, "base_url")
        record["backend_host"] = urlparse(base).netloc
        record["front_door"] = public_front_door_url(h, env)
        record["price_table"] = {"name": setup.price_table.name, "provider": setup.price_table.provider,
                                 "prices_verified": str(setup.price_table.prices_verified)}
        client = MonarchClient(base, token=env.get(h.credential_env or ""))
        checks.append(_check("backend", lambda: client.liveness() or _fail(f"{base}/api did not answer 200")))
        def health():
            if not client.token:
                client.login(h.login_email, env.get(h.login_password_env or ""))
            return client.health()
        checks.append(_check("session", health))
        checks.append(_check("knowledge_base", setup.arm().prepare))
        taught = getattr(setup.kb, "shim_public_url", None)
        checks.append(_check("front_door",
                             lambda: _front_door_agrees(record["front_door"], taught)))
        checks.append(_check("langfuse", lambda: _langfuse_health(h, env)))
    record["ok"] = all(c["ok"] for c in checks)
    write_json(probe_path(studio), record)
    return record


def _fail(message: str):
    raise RuntimeError(message)


def _front_door_agrees(configured: str, taught: str | None) -> None:
    """Refuse when the environment and the knowledge base name different doors.

    Monarch calls the address its seeds were taught; the harness hands the engine
    the address the environment names. When those differ the attempt authors fine
    and then executes against a door with nothing behind it -- which is how two
    rounds on 9 Sep spent US$ 18.75 measuring nothing while every check was green.
    """
    if not taught:
        return
    if configured.rstrip("/") != taught.rstrip("/"):
        raise ValueError(
            f"the environment names {configured} but the knowledge base was taught "
            f"{taught}; an attempt would execute against a door the seeds do not name")


def _check(name: str, call) -> dict:
    try:
        call()
    except (InfraError, RuntimeError, OSError, ValueError, Stop) as exc:
        message = getattr(exc, "message", None) or str(exc)
        return {"name": name, "ok": False, "detail": message[:300]}
    return {"name": name, "ok": True, "detail": "OK"}


def _langfuse_health(harness, env: dict) -> None:
    import base64
    url = expand(harness.langfuse_url, env, "langfuse_url") + "/api/public/health"
    keys = f"{env.get(harness.langfuse_public_key_env or '')}:{env.get(harness.langfuse_secret_key_env or '')}"
    req = urllib.request.Request(url, headers={"Authorization": "Basic " + base64.b64encode(keys.encode()).decode()})
    try:
        with urllib.request.urlopen(req, timeout=10.0) as response:
            if response.status != 200:
                raise RuntimeError(f"{url}: HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{url}: HTTP {exc.code}") from None
    except OSError as exc:
        raise RuntimeError(f"{url}: {exc}") from None


# -- readiness and the version record ------------------------------------------------

def readiness(studio, setup: Setup | None = None, probe: dict | None = None) -> tuple[dict, dict | None]:
    """The three-axis readiness of the stock version, and the probe it rests on (if any)."""
    setup = setup or Setup(studio)
    probe = load_probe(studio) if probe is None else probe
    source = "frozen" if setup.checkout else "source_required"
    if not setup.ok:
        return rm.readiness(source, "not_applicable", "blocked", setup.problems), probe
    if probe is None:
        return rm.readiness(source, "not_applicable", "preparation_required",
                            ["Verify the Monarch connection before launching: the deployment, its session, "
                             "the knowledge base and Langfuse are checked and recorded."]), None
    try:
        checked = datetime.fromisoformat(probe["checked_at"])
    except (KeyError, ValueError, TypeError):
        checked = None
    if checked is None or _now() - checked > PROBE_TTL:
        return rm.readiness(source, "not_applicable", "preparation_required",
                            ["The last verification is older than two hours; verify the Monarch connection again."]), probe
    if probe.get("version") != setup.version:
        return rm.readiness(source, "not_applicable", "preparation_required",
                            [f"The checkout moved since the last verification ({probe.get('version')} then, {setup.version} now); verify again."]), probe
    failed = [c for c in probe.get("checks", []) if not c.get("ok")]
    if failed or not probe.get("ok"):
        return rm.readiness(source, "not_applicable", "blocked",
                            [f"{c['name']}: {c['detail']}" for c in failed] or ["The last verification failed."]), probe
    notes = []
    if not setup.stock:
        notes.append(f"Custom build: {setup.version} is not a clean main checkout; results are not stock results.")
    notes.append("Provider path is declared by the price table, not observed; the served build is named from the local checkout.")
    return rm.readiness(source, "not_applicable", "ready", notes), probe


def manifest(setup: Setup, probe: dict | None) -> dict | None:
    """The executable identity of what would run: checkout, harness, knowledge base, price table."""
    if not setup.ok or not setup.checkout:
        return None
    kb_hash = hashlib.sha256(json.dumps(setup.kb.kb, sort_keys=True).encode()).hexdigest()
    if setup.checkout.get("declared") and not setup.checkout.get("commit"):
        # Declared by the operator without a commit: an identity, not a frozen git source.
        source = {"kind": "none", "repository": ENTERPRISE_REPOSITORY, "directory": ENTERPRISE_DIRECTORY,
                  "ref": None, "commit": None, "patch_sha256": None, "lockfile": None, "image_digest": None,
                  "declared_build": setup.checkout["version"]}
    else:
        source = {"kind": "git", "repository": ENTERPRISE_REPOSITORY, "directory": ENTERPRISE_DIRECTORY,
                  "ref": setup.checkout["branch"], "commit": setup.checkout["commit"],
                  "patch_sha256": setup.checkout["patch_sha256"], "lockfile": None, "image_digest": None}
    built = rm.build(IDENTITY,
                     source=source,
                     runtime={"entrypoint": "wb_arms.monarch.MonarchArm", "dependency_closure": [],
                              "deployment_host": (probe or {}).get("backend_host"),
                              "note": "Served build named from the checkout the harness points at; the deployment is assumed built from it."},
                     evaluation={"track": "create-and-run", "provider": setup.price_table.provider, "model": None,
                                 "effort": "default", "harness": "monarch-enterprise-recipes",
                                 "harness_version": setup.version,
                                 "settings": {"authoring_mode": setup.harness.authoring_mode,
                                              "price_table": setup.price_table.name,
                                              "provider_declared_not_observed": True}},
                     artifacts={"knowledge_base": {"status": "present", "sha256": kb_hash, "path": str(setup.kb_path.name)}},
                     public_surface={"front_door": None},
                     budget_policy={"attempt_ceiling_usd": str(setup.ceiling()), "timeout_s": ATTEMPT_TIMEOUT_S},
                     readiness_record=rm.readiness("frozen", "not_applicable", "adapter_required", ["identity only"]),
                     notes="Stock Monarch Enterprise driven through its own API; custom builds are named as such.")
    return rm.freeze(built)


def version_record(studio) -> dict:
    """What the picker, the launcher and the job need to know about this version."""
    setup = Setup(studio)
    ready, probe = readiness(studio, setup)
    name = "Default Monarch Enterprise"
    served = None
    if setup.version:
        served = {"version": setup.version, "stock": setup.stock, "checkout": setup.checkout,
                  "checked_at": (probe or {}).get("checked_at"), "backend_host": (probe or {}).get("backend_host"),
                  "price_table": (probe or {}).get("price_table")}
        name = ("Monarch Enterprise · " if setup.stock else "Monarch Enterprise (custom build) · ") + setup.version
    return {"served": served, "name": name, "readiness": ready, "probe": probe,
            "request_ceiling_usd": str(setup.ceiling()) if setup.ok else None,
            "manifest": manifest(setup, probe), "problems": setup.problems}


# -- the arm ------------------------------------------------------------------------

def build_arm(studio, identity: str, arm_id: str, task_id: str, cancel, maximum: Decimal, expected: dict | None):
    """The competitor for one attempt; refuses to run on a moved identity."""
    setup = Setup(studio)
    if not setup.ok:
        raise ValueError("Monarch Enterprise is not configured: " + "; ".join(setup.problems))
    current = manifest(setup, load_probe(studio))
    if expected and current and current["identity_sha256"] != expected.get("identity_sha256"):
        raise ValueError("The Monarch checkout, knowledge base or price table changed since this run was created")
    return EnterpriseArm(studio, identity, arm_id, task_id, cancel, maximum, setup)


_STATUS_WORDS = {"pending": "Waiting", "running": "Running", "succeeded": "Done", "failed": "Failed",
                 "skipped": "Skipped", "blocked": "Blocked"}


def recipe_nodes(recipe: dict | None) -> list[dict]:
    """The recipe's nodes in a shape the Activity lane can draw, whatever the recipe version."""
    nodes = []
    if not isinstance(recipe, dict):
        return nodes
    for index, step in enumerate(recipe.get("steps") or recipe.get("nodes") or []):
        if not isinstance(step, dict):
            continue
        identity = str(step.get("id") or step.get("stepId") or step.get("key") or f"step-{index + 1}")
        label = str(step.get("label") or step.get("name") or step.get("title") or step.get("action") or identity)
        nodes.append({"id": identity, "label": label,
                      "product": step.get("productSlug") or step.get("product") or step.get("app"),
                      "kind": step.get("kind") or step.get("type")})
    return nodes


class EnterpriseArm:
    """One attempt of the stock competitor, watched and billed by the Studio."""
    provider_key = "monarch"
    message_evidence = "normalized"

    def __init__(self, studio, identity: str, arm_id: str, task_id: str, cancel, maximum: Decimal, setup: Setup):
        self.studio, self.identity, self.name, self.task_id = studio, identity, arm_id, task_id
        self.cancel, self.maximum, self.setup = cancel, maximum, setup
        self.inner = setup.arm()
        self.model_label = self.inner.name
        self.output = ""
        self.sequence = 0
        self.frames = 0
        self.step = "authoring"
        self.recipe_summary = ""
        self.node_states: dict[str, str] = {}
        self.recipe_labels: dict[str, str] = {}   # node id -> the recipe's label, for step rows that carry only the id

    def emit(self, kind, **data):
        try:
            return self.studio.emit(self.identity, kind, model=self.name, task=self.task_id, **data)
        except OSError as exc:
            raise EvidenceWriteError("Live evidence could not be persisted") from exc

    # -- the observer: Monarch's progress as Activity events ---------------------

    def observe(self, kind: str, **d) -> None:
        if kind == "authoring_started":
            self.step = "authoring"
            self.emit("step_started", step="authoring", label="Build the workflow", step_type="monarch")
        elif kind == "authoring_frame":
            frame = d["frame"]
            self.frames += 1
            node = f"authoring:frame-{self.frames}"
            status = frame.get("status")
            if status == "awaiting_input":
                questions = [q.get("text") or q.get("label") or "" for q in (frame.get("awaiting_reply") or {}).get("questions") or []]
                label, output = f"Builder asked {len(questions)} question(s)", "\n".join(questions) or frame.get("message") or ""
            elif status == "error":
                label, output = "Builder stopped with an error", str(frame.get("error") or frame.get("message") or "")
            elif status == "done":
                label, output = "Builder finished", frame.get("message") or (f"Workflow {frame.get('workflowId')} version {frame.get('recipeVersion')}" if frame.get("workflowId") else "No workflow was built")
            else:
                label, output = f"Builder: {frame.get('phase') or status or 'working'}", frame.get("message") or ""
            self.emit("node_started", node=node, label=label, category="builder", step="authoring", phase=frame.get("phase"))
            self.emit("node_finished", node=node, label=label, category="builder", step="authoring",
                      status="error" if status == "error" else "completed", output=output)
        elif kind == "authoring_reply":
            node = f"authoring:reply-{d.get('request_id') or self.frames}"
            self.emit("node_started", node=node, label="Bench answered with the fixed sentence", category="builder", step="authoring")
            self.emit("node_finished", node=node, label="Bench answered with the fixed sentence", category="builder", step="authoring",
                      status="completed", output=d.get("text"), questions=d.get("questions"))
        elif kind == "authoring_finished":
            nodes = recipe_nodes(d.get("recipe"))
            if d.get("workflow_id"):
                self.recipe_summary = f"Workflow {d['workflow_id']} version {d.get('recipe_version')}, {len(nodes)} node(s)"
                self.emit("step_finished", step="authoring", label="Build the workflow", status="completed", output=self.recipe_summary,
                          workflow_id=d["workflow_id"], recipe_version=d.get("recipe_version"), questions=d.get("questions"))
            else:
                self.emit("step_finished", step="authoring", label="Build the workflow", status="error",
                          output=d.get("error") or "No workflow was built", questions=d.get("questions"))
        elif kind == "run_started":
            self.step = "execution"
            nodes = recipe_nodes(d.get("recipe"))
            self.recipe_labels = {n["id"]: n["label"] for n in nodes}
            self.emit("step_started", step="execution", label="Run the workflow", step_type="monarch", run_id=d.get("run_id"))
            self.emit("workflow_recipe", step="execution", run_id=d.get("run_id"), workflow_id=d.get("workflow_id"), nodes=nodes)
        elif kind == "run_step":
            step = d["step"]
            status = str(step.get("status") or "pending")
            self.node_states[step["stepId"]] = status
            label = step.get("label") if step.get("label") and step.get("label") != step["stepId"] else self.recipe_labels.get(step["stepId"], step["stepId"])
            self.emit("workflow_step", step="execution", node=f"wf:{step['stepId']}", label=label,
                      product=step.get("productSlug"), node_kind=step.get("kind"), status=status, message=step.get("message"),
                      progress=step.get("progress"), error_code=step.get("errorCode"), http_status=step.get("httpStatus"),
                      rendered=step.get("rendered"))
        elif kind == "run_finished":
            view = d.get("view") or {}
            counts = {}
            for state in self.node_states.values():
                counts[state] = counts.get(state, 0) + 1
            summary = ", ".join(f"{n} {_STATUS_WORDS.get(s, s).lower()}" for s, n in sorted(counts.items())) or "no node states reported"
            head = view.get("summary") or view.get("error") or f"Run {view.get('status') or 'ended'}"
            output = head + (f" ({summary})" if counts else "")
            self.emit("step_finished", step="execution", label="Run the workflow", status=d.get("status"),
                      output=output, run_status=view.get("status"),
                      error_code=view.get("errorCode"), error_node=view.get("errorNodeId"))

    # -- the attempt -------------------------------------------------------------

    def run(self, ep, deadline=None) -> ArmResult:
        original = ep._observe

        def observe(tool, arguments, call):
            node = f"{self.step}:tool-{self.sequence}"
            self.sequence += 1
            self.emit("node_started", node=node, label=tool, arguments=arguments, step=self.step)
            try:
                value = original(tool, arguments, call)
                self.emit("node_finished", node=node, label=tool, output=value, status="completed", step=self.step)
                return value
            except Exception:
                self.emit("node_finished", node=node, label=tool, output="Tool failed; inspect the retained trace.", status="error", step=self.step)
                raise
        ep._observe = observe
        self.inner.observer = self.observe
        ceiling = self.setup.ceiling()
        reservation = f"{self.identity}-{self.task_id}-{self.name}-monarch-{ep.episode_id.rsplit('/t', 1)[-1]}"
        reservation = "".join(ch if ch.isalnum() or ch in "._:-" else "_" for ch in reservation)[:120]
        self.studio.ledger.reserve(reservation, ceiling, scope_id=self.identity, scope_limit_usd=self.maximum,
                                   metadata={"harness": "monarch-enterprise", "version": self.inner.name, "task": self.task_id,
                                             "purpose": "one create + run attempt; settled from Langfuse"})
        self.studio.ledger.claim(reservation)
        self.emit("billing", billing={"reservation_id": reservation, "maximum_usd": str(ceiling), "status": "reserved",
                                      "harness": "monarch-enterprise", "version": self.inner.name}, budget=self.studio.budget())
        result: ArmResult | None = None
        try:
            result = self.inner.run(ep)
            return result
        except (InfraError, EpisodeTimeout) as exc:
            result = getattr(exc, "partial", None)
            self.emit("attempt_error", message=str(exc)[:300], step=self.step)
            raise
        finally:
            self._settle(reservation, ceiling, result)

    def _settle(self, reservation: str, ceiling: Decimal, result: ArmResult | None) -> None:
        known = (result is not None and not self.inner._price_unknown
                 and "cost_missing" not in result.flags and isinstance(result.cost_usd, (int, float)))
        actual = Decimal(str(result.cost_usd)).quantize(Decimal("0.000001")) if known else None
        self.studio.ledger.settle(reservation, actual, trace_ids=list(self.inner._trace_ids),
                                  outcome='error' if self.inner._infra or result is None else 'completed')
        if result is not None and actual is None and "billing=unknown" not in result.flags:
            result.flags.append("billing=unknown")
        if result is not None:
            self.output = self._summary(result)
            result.final_text = result.final_text or self.output
        status = "estimated_from_langfuse" if actual is not None else "unknown_hold"
        self.emit("billing", billing={"reservation_id": reservation, "maximum_usd": str(ceiling),
                                      "actual_usd": None if actual is None else str(actual), "status": status,
                                      "invoice_verified": False}, budget=self.studio.budget())

    def _summary(self, result: ArmResult) -> str:
        parts = [self.recipe_summary or "No workflow was built"]
        if result.error:
            parts.append(f"Ended with {result.termination}: {result.error}")
        else:
            parts.append("The workflow ran to completion; see the task checks for the verdict.")
        if "cost_missing" in result.flags:
            parts.append("Cost could not be read from Langfuse; the reservation stays held.")
        return " ".join(parts)
