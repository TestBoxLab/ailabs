"""Native harnesses behind a network-disabled container and scoped credential broker.

Only the broker has provider credentials and the episode object. No evaluator
file, snapshot, grading endpoint or other attempt is exported to the container.
The native event stream is retained as observation, never used as billing proof.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import time
from decimal import Decimal
import threading
from urllib.request import Request, HTTPRedirectHandler, build_opener

from wb_arms import providers
from wb_arms.api_loop import ArmResult, InfraError, _exec_tool, build_tools_anthropic
from wb_arms.cli_claude_code import parse_result
from wb_arms.native_sandbox import DockerRuntime, NATIVE_VERSIONS
from wb_arms.reservations import receipt_cost
from wb_studio.gateways import ceiling_cost, resolve_effort

MAX_BODY = 4 * 1024 * 1024
MAX_OUTPUT_TOKENS = 32768


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _transport(provider, path, body, *, timeout=120):
    """Only literal, provider-owned URLs; no incoming auth/header is forwarded."""
    host = "https://api.anthropic.com" if provider.adapter == "anthropic" else "https://api.openai.com"
    key = providers.api_key(provider)
    if not key:
        raise ValueError("The selected native provider credential is unavailable")
    headers = {"Content-Type": "application/json"}
    if provider.adapter == "anthropic":
        headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
    else:
        headers["Authorization"] = "Bearer " + key
    request = Request(host + path, data=json.dumps(body).encode(), headers=headers)
    with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
        raw = response.read(MAX_BODY + 1)
        if len(raw) > MAX_BODY:
            raise ValueError("Native provider response exceeded evidence limit")
        return response.status, response.headers.get("Content-Type", "application/json"), raw


def runtime_directory(studio):
    """A worker's accepted native image stays on its host, outside temporary jobs."""
    return Path(os.environ.get("STUDIO_NATIVE_RUNTIME_DIR") or studio.directory / "native-runtime")


def admitted_transport(studio, cancel=None, deadline=None):
    def send(provider, path, body):
        timeout = min(120, max(0, deadline - time.monotonic())) if deadline else 120
        if timeout <= 0:
            raise InfraError("infra:timeout", "Native provider deadline reached", retryable=False)
        requested_output = body.get("max_tokens", body.get("max_output_tokens", MAX_OUTPUT_TOKENS))
        tokens = len(json.dumps(body).encode()) * 2 + 1024 + requested_output
        with studio.runtime.provider(provider.family or provider.key, timeout=timeout, cancel=cancel, tokens=tokens) as remaining:
            return _transport(provider, path, body, timeout=min(timeout, remaining))
    return send


def _usage(provider, raw, content_type):
    """Read complete terminal usage from the provider response, not the native CLI."""
    if "text/event-stream" in content_type:
        events = [json.loads(line[5:].strip()) for line in raw.decode().splitlines()
                  if line.startswith("data:") and line[5:].strip() != "[DONE]"]
        if provider.adapter == "anthropic":
            start = next(e["message"]["usage"] for e in events if e.get("type") == "message_start")
            delta = next(e["usage"] for e in reversed(events) if e.get("type") == "message_delta" and "usage" in e)
            if not any(e.get("type") == "message_stop" for e in events):
                raise ValueError("Missing terminal provider event")
            usage = {**start, **delta}
        else:
            completed = next(e["response"] for e in events if e.get("type") == "response.completed")
            usage = completed["usage"]
    else:
        data = json.loads(raw)
        if provider.adapter != "anthropic" and data.get("status") != "completed":
            raise ValueError("Provider response is not completed")
        usage = data["usage"]
    if provider.adapter == "anthropic":
        cached, write = usage.get("cache_read_input_tokens", 0), usage.get("cache_creation_input_tokens", 0)
        prompt = usage["input_tokens"] + cached + write
    else:
        prompt, cached, write = usage["input_tokens"], usage.get("input_tokens_details", {}).get("cached_tokens", 0), 0
    return {"prompt_tokens": prompt, "cached_tokens": cached, "cache_write_tokens": write, "output_tokens": usage["output_tokens"]}


def _unsupported_content(value):
    if isinstance(value, dict):
        if value.get("type") in ("image", "input_image", "input_file", "file", "document"):
            return True
        if value.get("type") == "ephemeral" and value.get("ttl") not in (None, "5m"):
            return True
        return any(_unsupported_content(item) for item in value.values())
    return isinstance(value, list) and any(_unsupported_content(item) for item in value)


def _reply(status, value):
    return {"status": status, "content_type": "application/json", "body": base64.b64encode(json.dumps(value).encode()).decode()}


class NativeBroker:
    """Task-only application access and one admitted provider request at a time."""
    def __init__(self, episode, ledger, *, scope_id, maximum, model_key, prefix, observe, transport=None, cancel=None, max_requests=20):
        self.episode, self.ledger, self.scope_id, self.maximum = episode, ledger, scope_id, maximum
        self.provider, self.prefix, self.observe = providers.get(model_key), prefix, observe
        self.transport, self.cancel = transport or _transport, cancel
        self.max_requests = max_requests
        self.lock, self.sequence, self.receipts = threading.Lock(), 0, []

    def __call__(self, message):
        with self.lock:
            if self.cancel is not None and self.cancel.is_set():
                return _reply(409, {"error": "Attempt cancelled"})
            body, path = message.get("body"), message.get("path")
            if not isinstance(body, dict) or len(json.dumps(body).encode()) > MAX_BODY:
                return _reply(413, {"error": "Invalid or oversized relay request"})
            if path == "/tool":
                name, args = body.get("name"), body.get("arguments", {})
                if name not in ("api_search", "api_fetch", "base64_encode") or not isinstance(args, dict):
                    return _reply(403, {"error": "Only task application tools are exposed"})
                output = _exec_tool(self.episode, name, args)
                return _reply(200, {"output": output})
            allowed = {"/v1/messages", "/v1/messages?beta=true"} if self.provider.adapter == "anthropic" else {"/v1/responses"}
            if path not in allowed or body.get("model") != self.provider.model_id:
                return _reply(403, {"error": "Provider endpoint or model is outside the frozen attempt"})
            # No server-side tools or background jobs may create unbounded charges.
            tool_list = body.get("tools", [])
            if (body.get("background") or _unsupported_content(body) or not isinstance(tool_list, list)
                    or any(not isinstance(t, dict) or t.get("type") not in (None, "function", "custom") for t in tool_list)):
                return _reply(403, {"error": "Only native client-executed tools are permitted"})
            cap_field = "max_tokens" if self.provider.adapter == "anthropic" else "max_output_tokens"
            body = dict(body)
            if cap_field not in body:
                body[cap_field] = MAX_OUTPUT_TOKENS
            cap = body[cap_field]
            if type(cap) is not int or not 1 <= cap <= MAX_OUTPUT_TOKENS:
                return _reply(403, {"error": "Native output cap exceeds the declared attempt limit"})
            run = self.ledger.run_reservation(self.scope_id)
            if run is None or run.closed_at is not None:
                return _reply(409, {"error": "The complete run liability must be admitted before native requests"})
            if self.sequence >= self.max_requests:
                return _reply(403, {"error": "Native provider request limit reached"})
            self.sequence += 1
            identity = f"{self.prefix}#native-{self.sequence}"
            # UTF-8 bytes * 2 is a conservative text token upper bound; tool schemas
            # and native system prompts are included. No images/remote file fetches.
            maximum = ceiling_cost(self.provider, len(json.dumps(body).encode()) * 2 + 1024, cap)
            self.ledger.reserve(identity, maximum, scope_id=self.scope_id, scope_limit_usd=self.maximum,
                                metadata={"harness": "native-broker", "model": self.provider.model_id,
                                          "billing_provider": self.provider.family or self.provider.key, "max_output_tokens": cap})
            self.ledger.claim(identity)
            self.observe({"type": "native_provider_request", "request_id": identity, "path": path, "body": body})
            try:
                status_code, content_type, raw = self.transport(self.provider, path, body)
                self.observe({"type": "native_provider_response", "request_id": identity, "status": status_code,
                              "content_type": content_type, "body": raw.decode(errors="replace")})
                try:
                    usage = _usage(self.provider, raw, content_type) if status_code == 200 else None
                    actual = receipt_cost(self.provider, usage) if usage else None
                except (ValueError, KeyError, TypeError, StopIteration):
                    usage, actual = None, None
                from wb_arms.reservations import usage_details
                self.ledger.settle(identity, actual, usage=usage_details(usage),
                                   outcome='completed' if status_code == 200 else 'error')
                self.receipts.append({"id": identity, "usage": usage, "cost": actual})
                return {"status": status_code, "content_type": content_type, "body": base64.b64encode(raw).decode()}
            except Exception:
                reservation = next(r for r in self.ledger.reservations(scope_id=self.scope_id) if r.reservation_id == identity)
                self.ledger.settle(identity, reservation.actual_usd, outcome='error')
                self.observe({"type": "native_provider_error", "request_id": identity, "billing": "unknown_hold"})
                self.receipts.append({"id": identity, "usage": None, "cost": None})
                return _reply(502, {"error": "Provider request failed; billing hold retained"})


def status(studio):
    """Fast display status from local acceptance; launch always runs fresh probes."""
    folder = runtime_directory(studio)
    try:
        image_path, acceptance_path = folder / "image.json", _acceptance_path(studio)
        if not image_path.exists():
            raise ValueError("Native container has not been built and verified")
        if not acceptance_path.exists():
            raise ValueError("Native end-to-end acceptance has not passed; run native verify")
        image = json.loads(image_path.read_text(encoding="utf-8"))
        record = json.loads(acceptance_path.read_text(encoding="utf-8"))
        if (record.get("contract") != "native-isolation-v2" or record.get("image") != image.get("image")
                or record.get("source_sha256") != _acceptance_sources()
                or record.get("offline_tests", {}).get("exit_code") != 0
                or any(record.get("harnesses", {}).get(h, {}).get("application_tool_observed") is not True for h in NATIVE_VERSIONS)):
            raise ValueError("Native acceptance differs from the current runtime; rerun native verify")
        return {"status": "ready", "launchable": True, "image": image["image"], "versions": NATIVE_VERSIONS,
                "verification": "recorded_acceptance", "verified_at": record.get("verified_at"),
                "reason": "Native acceptance is recorded; every launch freshly checks the container boundary."}
    except (OSError, ValueError, KeyError) as exc:
        return {"status": "blocked", "launchable": False, "reason": str(exc), "versions": NATIVE_VERSIONS}


def freeze(studio, runner):
    """Prepare a frozen runtime identity; this does not authorize paid dispatch."""
    harness = runner.get("harness") or runner.get("provider")
    if harness not in NATIVE_VERSIONS:
        raise ValueError("Select Claude Code or Codex")
    provider = providers.get(runner["model"])
    if provider.adapter != ("anthropic" if harness == "claude-code" else "openai_responses"):
        raise ValueError("Native harness must match the model family")
    manifest = require_acceptance(studio, harness)
    from wb_arms.runtime_manifest import sha256_json
    return {"image": manifest["image"], "helper_sha256": manifest["helper_sha256"],
            "acceptance_sha256": sha256_json(manifest["acceptance"]),
            "harness": harness, "native_version": NATIVE_VERSIONS[harness], "harness_version": NATIVE_VERSIONS[harness], "kind": "native-harness",
            "tools_sha256": sha256_json(build_tools_anthropic()), "model_version": provider.model_id,
            "model_version_qualification": "Pinned provider model identifier; provider alias updates are not an immutable model-weight snapshot",
            "model_key": provider.key, "model": provider.model_id, "effort": resolve_effort(provider, runner.get("effort", "default")),
            "limits": {"seconds": 900, "max_output_tokens": MAX_OUTPUT_TOKENS, "memory": "2g", "cpus": 2},
            "qualification": "Native harness with task-only tools; no workflow methodology. Buffered provider streaming relay."}


class NativeArm:
    """Prepared native execution adapter; public launch remains fail-closed pending acceptance."""
    message_evidence = "native-stream-and-provider-receipts"

    def __init__(self, studio, identity, manifest, task, cancel, maximum):
        self.studio, self.identity, self.manifest, self.task_id = studio, identity, manifest, task
        self.cancel, self.maximum = cancel, maximum
        self.name = manifest["harness"] + "/" + manifest["model_key"]
        self.provider_key, self.output = manifest["model_key"], ""

    def run(self, ep, deadline=None):
        # This reads a source/image-bound record produced by real offline checks;
        # an environment flag or caller assertion never opens native execution.
        accepted = require_acceptance(self.studio, self.manifest["harness"])
        if accepted["image"] != self.manifest["image"]:
            raise ValueError("Native image changed after the job was frozen")
        return self._execute_verified(ep, deadline)

    def _execute_verified(self, ep, deadline=None):
        """Internal acceptance path; no host launch or alternative credentials."""
        run = self.studio.ledger.run_reservation(self.identity)
        if run is None or run.closed_at is not None:
            raise ValueError("The complete run liability must be reserved before native execution")
        runtime = DockerRuntime(runtime_directory(self.studio))
        current = runtime.verify()
        if current["image"] != self.manifest["image"]:
            raise ValueError("Native image changed since this attempt was frozen")
        def observe(entry):
            ep.record_agent_event(entry)
            self.studio.emit(self.identity, "native_event", task=self.task_id, model=self.name, event=entry)
        settings = self.studio.job(self.identity)["settings"].get("configuration", {})
        broker = NativeBroker(ep, self.studio.ledger, scope_id=self.identity, maximum=self.maximum,
                              model_key=self.provider_key, prefix=ep.episode_id, observe=observe, cancel=self.cancel,
                              transport=admitted_transport(self.studio, self.cancel, deadline), max_requests=settings.get("max_turns", 20))
        tools = [{"name": t["name"], "description": t["description"], "inputSchema": t["input_schema"]} for t in build_tools_anthropic()]
        settings = self.studio.job(self.identity)["settings"].get("configuration", {})
        prompt = ep.task["prompt"][0]["content"] + "\n\n" + ep.task["prompt"][1]["content"]
        if settings.get("prompt"):
            prompt += "\n\nExperiment instructions:\n" + settings["prompt"]
        config = {"harness": self.manifest["harness"], "model": self.manifest["model"], "effort": self.manifest["effort"],
                  "tools": tools, "max_turns": settings.get("max_turns", 20), "prompt": prompt}
        events = runtime.execute(config, broker, observe, cancel=self.cancel, deadline=deadline)
        stdout = "".join(e["text"] for e in events if e.get("type") == "native_output" and e.get("stream") == "stdout")
        terminal = next((e for e in reversed(events) if e.get("type") == "native_exit"), None)
        if terminal is None:
            raise InfraError("infra:harness_crash", "Native terminal event is missing", retryable=False)
        if self.manifest["harness"] == "claude-code":
            result = parse_result(stdout, terminal["returncode"])
        else:
            parsed = [json.loads(line) for line in stdout.splitlines() if line.strip()]
            completed = terminal["returncode"] == 0 and any(e.get("type") == "turn.completed" for e in parsed)
            final = [e["item"]["text"] for e in parsed if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "agent_message"]
            result = ArmResult(termination="completed" if completed else "agent_error", final_text=final[-1] if final else None,
                               turn_log=[{"source": "codex_stream", "event": e} for e in parsed])
        result.flags = [flag for flag in result.flags if flag != "billing=unknown"]
        result.cost_usd = float(sum((r["cost"] for r in broker.receipts if r["cost"] is not None), Decimal(0)))
        if any(r["cost"] is None for r in broker.receipts) or not broker.receipts:
            result.flags.append("billing=unknown")
        for field, key in (("tokens_prompt", "prompt_tokens"), ("tokens_cached", "cached_tokens"),
                           ("tokens_cache_write", "cache_write_tokens"), ("tokens_output", "output_tokens")):
            setattr(result, field, sum(r["usage"][key] for r in broker.receipts if r["usage"] is not None))
        result.tool_calls = len(ep.tool_calls)
        self.output = result.final_text or ""
        return result


CONTAINER_HELPER = r'''
import base64,http.server,json,os,pathlib,queue,subprocess,sys,threading,urllib.request
LIMIT=8*1024*1024
if len(sys.argv)>1 and sys.argv[1]=='mcp':
 config=json.loads(pathlib.Path('/work/runtime.json').read_text())
 for line in sys.stdin:
  m=json.loads(line)
  if 'id' not in m: continue
  method=m.get('method')
  if method=='initialize': result={'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'task-applications','version':'1'}}
  elif method=='tools/list': result={'tools':config['tools']}
  elif method=='tools/call':
   req=urllib.request.Request('http://127.0.0.1:8123/tool',data=json.dumps(m['params']).encode(),headers={'Content-Type':'application/json'})
   try:
    with urllib.request.urlopen(req,timeout=180) as r: value=json.load(r)
    result={'content':[{'type':'text','text':value['output']}],'isError':value.get('is_error',False)}
   except Exception: result={'content':[{'type':'text','text':'Application gateway refused this request.'}],'isError':True}
  elif method=='ping': result={}
  else:
   print(json.dumps({'jsonrpc':'2.0','id':m['id'],'error':{'code':-32601,'message':'Unknown method'}}),flush=True);continue
  print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':result}),flush=True)
 sys.exit(0)
lock=threading.Lock(); responses={}; serial=0
def emit(v):
 line=json.dumps(v,separators=(',',':'))
 if len(line.encode())>LIMIT: raise ValueError('oversized relay output')
 with lock: sys.stdout.write(line+'\n');sys.stdout.flush()
config=json.loads(sys.stdin.readline(LIMIT));pathlib.Path('/work/runtime.json').write_text(json.dumps(config))
def receive():
 while True:
  line=sys.stdin.readline(LIMIT)
  if not line: os._exit(125)
  v=json.loads(line);target=responses.get(v.get('id'))
  if target: target.put(v)
threading.Thread(target=receive,daemon=True).start()
class Gateway(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def do_GET(self): self.send_error(403)
 def do_POST(self):
  global serial
  n=int(self.headers.get('Content-Length','0'))
  if not 0<n<LIMIT: self.send_error(413);return
  body=json.loads(self.rfile.read(n))
  with lock: serial+=1;identity=serial;target=queue.Queue();responses[identity]=target
  emit({'type':'request','id':identity,'path':self.path,'body':body})
  try:
   v=target.get(timeout=180);raw=base64.b64decode(v['body']);self.send_response(v['status'])
   self.send_header('Content-Type',v.get('content_type','application/json'));self.send_header('Content-Length',str(len(raw)))
   self.end_headers();self.wfile.write(raw)
  except Exception: self.send_error(502)
  finally: responses.pop(identity,None)
server=http.server.ThreadingHTTPServer(('127.0.0.1',8123),Gateway)
threading.Thread(target=server.serve_forever,daemon=True).start()
env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/home/agent','LANG':'C.UTF-8','TMPDIR':'/tmp',
 'ANTHROPIC_API_KEY':'local-relay-only','OPENAI_API_KEY':'local-relay-only','ANTHROPIC_BASE_URL':'http://127.0.0.1:8123','CLAUDE_CODE_MAX_OUTPUT_TOKENS':'32768',
 'CODEX_HOME':'/home/agent/.codex','DISABLE_AUTOUPDATER':'1','DISABLE_TELEMETRY':'1','DISABLE_ERROR_REPORTING':'1'}
pathlib.Path('/home/agent/.codex').mkdir(parents=True,exist_ok=True)
pathlib.Path('/work/.mcp.json').write_text(json.dumps({'mcpServers':{'applications':{'command':'python3','args':['/opt/native/helper.py','mcp']}}}))
if config['harness']=='claude-code':
 cmd=['claude','-p','--output-format','stream-json','--verbose','--model',config['model'],'--permission-mode','bypassPermissions',
  '--strict-mcp-config','--mcp-config','/work/.mcp.json','--settings','{"disableAllHooks":true}','--max-turns',str(config['max_turns'])]
 if config.get('effort'): cmd+=['--effort',config['effort']]
else:
 cmd=['codex','exec','--json','--skip-git-repo-check','--dangerously-bypass-approvals-and-sandbox','--model',config['model'],
  '-c','model_provider="ailabs"','-c','model_providers.ailabs.name="AI Labs isolated broker"',
  '-c','model_providers.ailabs.base_url="http://127.0.0.1:8123/v1"','-c','model_providers.ailabs.env_key="OPENAI_API_KEY"',
  '-c','model_providers.ailabs.wire_api="responses"','-c','mcp_servers.applications.command="python3"',
  '-c','mcp_servers.applications.args=["/opt/native/helper.py","mcp"]']
 if config.get('effort'): cmd+=['-c','model_reasoning_effort='+json.dumps(config['effort'])]
 cmd+=['-']
child=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,cwd='/work',text=True)
child.stdin.write(config['prompt']);child.stdin.close()
def capture(stream,name):
 for line in stream: emit({'type':'native_output','stream':name,'text':line})
threads=[threading.Thread(target=capture,args=(child.stdout,'stdout')),threading.Thread(target=capture,args=(child.stderr,'stderr'))]
for t in threads:t.start()
code=child.wait()
for t in threads:t.join()
emit({'type':'native_exit','returncode':code})
'''

# Acceptance is produced only by this offline verifier. It runs both real native
# CLIs against scripted HTTP replies and the real container application relay.
# No provider credentials or paid transport are involved in acceptance.
def _acceptance_sources():
    import hashlib
    from pathlib import Path
    import wb_arms.native_sandbox as sandbox
    files = {"native": Path(__file__), "sandbox": Path(sandbox.__file__),
             "tests": Path(__file__).parents[1] / "tests" / "test_studio_native_runtime.py",
             "budget": Path(__file__).parents[1] / "wb_orchestrator" / "budget.py"}
    return {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()}


def _acceptance_path(studio):
    return runtime_directory(studio) / "acceptance.json"


def require_acceptance(studio, harness):
    current = DockerRuntime(runtime_directory(studio)).verify()
    path = _acceptance_path(studio)
    if not path.exists():
        raise InfraError("infra:harness_crash", "Native end-to-end acceptance has not passed; run the offline native verify command", retryable=False)
    record = json.loads(path.read_text(encoding="utf-8"))
    if (record.get("contract") != "native-isolation-v2" or record.get("image") != current["image"]
            or record.get("source_sha256") != _acceptance_sources()
            or record.get("offline_tests", {}).get("exit_code") != 0
            or record.get("harnesses", {}).get(harness, {}).get("application_tool_observed") is not True):
        raise InfraError("infra:harness_crash", "Native acceptance differs from the current runtime; rerun native verify", retryable=False)
    return {**current, "acceptance": record}


def _scripted_reply(harness, model, tool_name, complete):
    if harness == "claude-code":
        content = [{"type": "text", "text": "READY"}] if complete else [{"type": "tool_use", "id": "call_boundary", "name": tool_name, "input": {"text": "boundary"}}]
        data = {"id": "msg_boundary", "type": "message", "role": "assistant", "model": model, "content": content,
                "stop_reason": "end_turn" if complete else "tool_use", "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 10}}
        events = [{"type": "message_start", "message": {**data, "content": [], "stop_reason": None}}]
        for index, item in enumerate(content):
            events.append({"type": "content_block_start", "index": index, "content_block": {**item, **({"text": ""} if complete else {"input": {}})}})
            events.append({"type": "content_block_delta", "index": index, "delta": {"type": "text_delta", "text": "READY"} if complete else {"type": "input_json_delta", "partial_json": '{"text":"boundary"}'}})
            events.append({"type": "content_block_stop", "index": index})
        events += [{"type": "message_delta", "delta": {"stop_reason": data["stop_reason"], "stop_sequence": None}, "usage": {"output_tokens": 10}}, {"type": "message_stop"}]
    else:
        content = {"type": "output_text", "text": "READY", "annotations": []}
        item = ({"type": "message", "id": "msg_boundary", "role": "assistant", "status": "completed", "content": [content]} if complete else
                {"type": "function_call", "id": "fc_boundary", "call_id": "call_boundary", "name": tool_name, "arguments": '{"text":"boundary"}', "status": "completed"})
        data = {"id": "resp_boundary" + ("2" if complete else "1"), "object": "response", "created_at": 1, "status": "completed", "model": model,
                "output": [item], "usage": {"input_tokens": 10, "output_tokens": 10, "total_tokens": 20}}
        events = [{"type": "response.created", "response": {**data, "status": "in_progress", "output": []}},
                  {"type": "response.output_item.added", "output_index": 0, "item": {**item, "status": "in_progress"}}]
        if complete:
            events += [{"type": "response.content_part.added", "item_id": item["id"], "output_index": 0, "content_index": 0, "part": {**content, "text": ""}},
                       {"type": "response.output_text.delta", "item_id": item["id"], "output_index": 0, "content_index": 0, "delta": "READY"},
                       {"type": "response.output_text.done", "item_id": item["id"], "output_index": 0, "content_index": 0, "text": "READY"},
                       {"type": "response.content_part.done", "item_id": item["id"], "output_index": 0, "content_index": 0, "part": content}]
        else:
            events += [{"type": "response.function_call_arguments.done", "item_id": item["id"], "output_index": 0, "arguments": item["arguments"]}]
        events += [{"type": "response.output_item.done", "output_index": 0, "item": item}, {"type": "response.completed", "response": data}]
    raw = "".join("event: " + e["type"] + "\ndata: " + json.dumps(e) + "\n\n" for e in events).encode()
    return {"status": 200, "content_type": "text/event-stream", "body": base64.b64encode(raw).decode()}


def verify_runtime(studio):
    import subprocess
    import sys
    from pathlib import Path
    from datetime import datetime, timezone
    runtime = DockerRuntime(runtime_directory(studio))
    manifest = runtime.verify()
    root = Path(__file__).parents[1]
    command = [sys.executable, "-m", "pytest", "tests/test_studio_native_runtime.py", "tests/test_native_sandbox.py", "-q"]
    tests = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=120)
    if tests.returncode != 0:
        raise InfraError("infra:harness_crash", "Native offline boundary regressions did not pass; no acceptance written", retryable=False)
    harnesses = {}
    for harness, model in (("claude-code", "claude-opus-5"), ("codex", "gpt-5.6-sol")):
        seen = {"provider_requests": 0, "application_tool_observed": False}
        evidence = []
        def request(message):
            body, path = message.get("body", {}), message.get("path")
            if path == "/tool":
                if body.get("name") != "base64_encode" or body.get("arguments") != {"text": "boundary"}:
                    raise ValueError("Acceptance CLI requested an unexpected application operation")
                seen["application_tool_observed"] = True
                return _reply(200, {"output": "Ym91bmRhcnk="})
            if path not in ("/v1/messages", "/v1/messages?beta=true", "/v1/responses") or body.get("model") != model:
                return _reply(403, {"error": "Offline acceptance only serves the pinned fixture model"})
            seen["provider_requests"] += 1
            if seen["provider_requests"] > 4:
                raise ValueError("Native acceptance did not terminate within four fixture replies")
            tools = body.get("tools", [])
            candidates = [t.get("name") or t.get("function", {}).get("name") for t in tools if isinstance(t, dict)]
            tool = next((name for name in candidates if name and name.endswith("base64_encode")), None)
            if not tool:
                # Native auxiliary requests may precede MCP initialization. They
                # still count toward the fixture bound and cannot satisfy acceptance.
                return _scripted_reply(harness, model, "", True)
            return _scripted_reply(harness, model, tool, seen["application_tool_observed"])
        tool = {"name": "base64_encode", "description": "Encode task text as base64", "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}
        events = runtime.execute({"harness": harness, "model": model, "effort": "low", "tools": [tool], "max_turns": 4,
                                  "prompt": "Encode boundary with the applications tool, then reply READY."}, request, evidence.append, deadline=time.monotonic() + 120)
        terminal = next((event for event in reversed(events) if event.get("type") == "native_exit"), None)
        text = "".join(event.get("text", "") for event in events)
        if not terminal or terminal["returncode"] != 0 or not seen["application_tool_observed"] or "READY" not in text:
            raise InfraError("infra:harness_crash", harness + " failed real native CLI/relay acceptance; no acceptance written", retryable=False)
        harnesses[harness] = {**seen, "version": NATIVE_VERSIONS[harness], "native_exit": terminal, "events": evidence}
    record = {"contract": "native-isolation-v2", "image": manifest["image"], "source_sha256": _acceptance_sources(),
              "verified_at": datetime.now(timezone.utc).isoformat(), "container_probe": manifest["probe"],
              "offline_tests": {"command": command, "exit_code": tests.returncode, "output": tests.stdout},
              "harnesses": harnesses, "provider_requests": "Scripted offline replies only; no provider credential was read"}
    from wb_results.evidence import write_json
    write_json(_acceptance_path(studio), record)
    return record


if __name__ == "__main__":
    import argparse
    from pathlib import Path
    from types import SimpleNamespace
    parser = argparse.ArgumentParser(description="Build and verify native container isolation without paid requests")
    parser.add_argument("command", choices=("build", "verify", "status"))
    parser.add_argument("--directory", type=Path, required=True, help="Studio data directory")
    args = parser.parse_args()
    studio = SimpleNamespace(directory=args.directory)
    if args.command == "build":
        result = DockerRuntime(runtime_directory(studio)).build()
    elif args.command == "verify":
        result = verify_runtime(studio)
    else:
        result = status(studio)
    print(json.dumps(result, indent=2, default=str))
