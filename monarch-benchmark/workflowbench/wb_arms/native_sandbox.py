"""Fail-closed native-harness isolation preflight.

This is a launch prohibition and a verification contract, NOT a sandbox. There
is deliberately no environment switch, caller-supplied attestation, or fallback
host launcher. A Docker executable/daemon and a separate working directory do
not prove isolation. Replace this gate only with an implemented runtime plus
adversarial boundary verification and evaluator-owned evidence capture.
"""
from __future__ import annotations

from dataclasses import dataclass

from wb_arms.api_loop import InfraError


@dataclass(frozen=True)
class NativePreflight:
    contract_version: str
    status: str
    missing_checks: tuple[str, ...]


# The future launcher must enforce all checks, not just accept these labels.
# runtime_identity: immutable image and native CLI version, validated runtime.
# filesystem_boundary: only public system/goal + agent-owned work; no evaluator
# source, grader, answers, snapshots, competitor traces, host mounts or sockets.
# environment_boundary: independent HOME/config; explicit minimal environment;
# no inherited host secrets, subscription sessions, hooks or personal settings.
# application_gateway: evaluator-owned external service exposing authorized app
# actions only; never give the agent a task file or snapshot-control endpoint.
# network_boundary: deny host/control-plane/other-competitor reachability; allow
# only scoped application and provider endpoints without container escape paths.
# evidence_capture: evaluator owns immutable event capture and final world state;
# native stdout is observed evidence, never authoritative grading or snapshots.
# billing_boundary: verified API-key billing via narrowly scoped credentials or
# broker; a held reservation covers the maximum attempt including retries.
_MISSING_CHECKS = (
    "runtime_identity", "filesystem_boundary", "environment_boundary",
    "application_gateway", "network_boundary", "evidence_capture", "billing_boundary",
)


def preflight() -> NativePreflight:
    """Read-only report; no supported isolated native runtime exists yet."""
    return NativePreflight("native-isolation-v1", "blocked", _MISSING_CHECKS)


def require_verified_runtime() -> None:
    """Reject every launch until the runtime contract has working enforcement."""
    report = preflight()
    raise InfraError(
        "infra:harness_crash",
        "Native launch blocked: no verified isolated runtime is implemented "
        f"({report.contract_version}); missing checks: {', '.join(report.missing_checks)}",
        retryable=False,
    )

# The historical host adapter remains prohibited. This container boundary is
# separately verified and never treats a host CLI install as native readiness.
import hashlib
import json
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
import uuid

NATIVE_VERSIONS = {"claude-code": "2.1.261", "codex": "0.153.4"}
MAX_RELAY_BYTES = 8 * 1024 * 1024


def container_command(image, name):
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("Native image must be pinned by its immutable SHA-256 identity")
    if not re.fullmatch(r"ailabs-native-[0-9a-f]{32}", name):
        raise ValueError("Invalid native container identity")
    return ["docker", "run", "--rm", "-i", "--name", name, "--network", "none", "--read-only",
            "--user", "65532:65532", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", "256", "--memory", "2g", "--cpus", "2", "--ipc", "none",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m,uid=65532,gid=65532",
            "--tmpfs", "/work:rw,nosuid,size=512m,uid=65532,gid=65532",
            "--tmpfs", "/home/agent:rw,nosuid,size=512m,uid=65532,gid=65532",
            "--workdir", "/work", "--entrypoint", "python3", image, "/opt/native/helper.py"]


class DockerRuntime:
    """No mounts or network; host-owned relay is the only application/provider path."""
    def __init__(self, directory):
        self.directory = Path(directory)

    def _command(self, args, **kwargs):
        return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=kwargs.pop("timeout", 30), **kwargs)

    def build(self):
        from wb_studio.native import CONTAINER_HELPER
        self.directory.mkdir(parents=True, exist_ok=True)
        base = "node:22-bookworm-slim"
        self._command(["docker", "pull", base], timeout=300).check_returncode()
        inspected = self._command(["docker", "image", "inspect", base, "--format", "{{json .RepoDigests}}"])
        inspected.check_returncode()
        digest = json.loads(inspected.stdout)[0]
        if "@sha256:" not in digest:
            raise ValueError("Base image has no immutable digest")
        # A new, minimal context for every build. Never send the repository to Docker.
        context = self.directory / ("context-" + uuid.uuid4().hex)
        context.mkdir()
        (context / "helper.py").write_text(CONTAINER_HELPER, encoding="utf-8", newline="\n")
        (context / "Dockerfile").write_text(
            f"FROM {digest}\nRUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates git && rm -rf /var/lib/apt/lists/*\n"
            f"RUN npm install -g @anthropic-ai/claude-code@{NATIVE_VERSIONS['claude-code']} @openai/codex@{NATIVE_VERSIONS['codex']}\n"
            "COPY helper.py /opt/native/helper.py\nUSER 65532:65532\nWORKDIR /work\n", encoding="utf-8", newline="\n")
        output = context / "image-id.txt"
        self._command(["docker", "build", "--iidfile", str(output), str(context)], timeout=600).check_returncode()
        record = {"image": output.read_text().strip(), "base_image": digest, "versions": NATIVE_VERSIONS,
                  "helper_sha256": hashlib.sha256(CONTAINER_HELPER.encode()).hexdigest()}
        (self.directory / "image.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        return self.verify()

    def verify(self):
        from wb_studio.native import CONTAINER_HELPER
        path = self.directory / "image.json"
        if not path.exists():
            raise InfraError("infra:harness_crash", "Native container has not been built and verified", retryable=False)
        record = json.loads(path.read_text(encoding="utf-8"))
        command = container_command(record["image"], "ailabs-native-" + uuid.uuid4().hex)
        probe = '''import hashlib,json,os,pathlib,socket,subprocess
assert os.getuid()==65532
assert not pathlib.Path('/var/run/docker.sock').exists()
assert not pathlib.Path('/workspace').exists()
assert not any(k in os.environ for k in ('ANTHROPIC_API_KEY','OPENAI_API_KEY','HOST_SECRET','AWS_SECRET_ACCESS_KEY'))
assert sorted(p.name for p in pathlib.Path('/sys/class/net').iterdir())==['lo']
assert not list(pathlib.Path('/home/agent').iterdir())
assert not list(pathlib.Path('/work').iterdir())
try:
 pathlib.Path('/opt/native/forbidden').write_text('x'); raise AssertionError('root filesystem writable')
except OSError: pass
print(json.dumps({'helper_sha256':hashlib.sha256(pathlib.Path('/opt/native/helper.py').read_bytes()).hexdigest(),
 'claude-code':subprocess.check_output(['claude','--version'],text=True).strip(),
 'codex':subprocess.check_output(['codex','--version'],text=True).strip()}))'''
        try:
            checked = self._command(command[:-1] + ["-c", probe], timeout=60)
            checked.check_returncode()
            evidence = json.loads(checked.stdout)
            expected = hashlib.sha256(CONTAINER_HELPER.encode()).hexdigest()
            if record.get("helper_sha256") != expected or evidence["helper_sha256"] != expected:
                raise ValueError("Native image helper differs from installed evaluator runtime")
            if evidence["claude-code"] != NATIVE_VERSIONS["claude-code"] + " (Claude Code)" or evidence["codex"] != "codex-cli " + NATIVE_VERSIONS["codex"]:
                raise ValueError("Native CLI versions differ from the pinned runtime")
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
            raise InfraError("infra:harness_crash", "Native isolation probe failed (" + type(exc).__name__ + ")", retryable=False) from exc
        return {**record, "probe": evidence, "container_boundary": "verified", "network": "none", "host_mounts": []}

    def execute(self, config, request, observe, *, cancel=None, deadline=None):
        manifest = self.verify()
        name = "ailabs-native-" + uuid.uuid4().hex
        process = subprocess.Popen(container_command(manifest["image"], name), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        messages = queue.Queue(maxsize=64)
        def read(stream, kind):
            while True:
                line = stream.readline(MAX_RELAY_BYTES + 1)
                if not line: break
                messages.put((kind, line))
            messages.put((kind, None))
        for stream, kind in ((process.stdout, "stdout"), (process.stderr, "stderr")):
            threading.Thread(target=read, args=(stream, kind), daemon=True).start()
        output, ended, total_bytes = [], False, 0
        deadline = min(deadline or time.monotonic() + 900, time.monotonic() + 900)
        try:
            process.stdin.write(json.dumps(config).encode() + b"\n"); process.stdin.flush()
            while not ended:
                if (cancel is not None and cancel.is_set()) or time.monotonic() >= deadline:
                    raise InfraError("infra:timeout", "Native attempt cancelled or deadline reached", retryable=False)
                try: kind, line = messages.get(timeout=.2)
                except queue.Empty:
                    if process.poll() is not None: break
                    continue
                if line is None:
                    if kind == "stdout": ended = True
                    continue
                total_bytes += len(line)
                if len(line) > MAX_RELAY_BYTES or total_bytes > 128 * 1024 * 1024:
                    raise ValueError("Native evidence exceeded its declared bound")
                if kind == "stderr":
                    observe({"type": "native_runtime_stderr", "text": line.decode(errors="replace")}); continue
                message = json.loads(line)
                if message.get("type") == "request":
                    reply = request(message)
                    process.stdin.write(json.dumps({"id": message["id"], **reply}).encode() + b"\n"); process.stdin.flush()
                elif message.get("type") in ("native_output", "native_exit"):
                    observe(message); output.append(message)
                else: raise ValueError("Unknown native relay message")
            code = process.wait(timeout=10)
            if code != 0:
                raise InfraError("infra:harness_crash", "Native container exited without a complete result", retryable=False)
            return output
        finally:
            # Kill all container descendants, not just the local Docker client.
            try: self._command(["docker", "rm", "--force", name], timeout=30)
            finally:
                if process.poll() is None: process.kill()
                process.wait(timeout=10)
