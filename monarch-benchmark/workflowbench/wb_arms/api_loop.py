"""Generic tool-loop arm for API models, in-process against the Episode.

Cache discipline (the whole point of this file's structure):
- Byte-stable prefix: system prompt -> tools array -> task brief -> append-only
  history. Tools are built once per run with a canonical serialization; earlier
  messages are never mutated or re-ordered.
- No timestamps, run ids, or episode ids in the system prompt or tool schemas;
  per-task variables live in the first user message only.
- From turn 3 on, cached_tokens >= 0.8 * previous turn's prompt_tokens, else
  the episode is flagged cache_degraded with the first divergent message index.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from wb_arms import providers
from wb_arms.providers import Provider
from wb_world.episode import Episode, EvidenceWriteError

MAX_TOOL_TURNS = 50  # the AB budget
MAX_TOOL_RESULT_CHARS = 100_000  # context guard; truncation is marked, never silent

# Deterministic tool schemas: plain dicts, canonically serialized. Never add
# anything episode- or run-specific here.
_TOOL_DEFS = [
    {
        "name": "api_search",
        "description": ("Search available API endpoints by keyword. Use before api_fetch. "
                        "Returns JSON with matching endpoints: id, method, url, description, "
                        "parameters, request body, and response format."),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword query, e.g. 'salesforce update contact'."},
                "top_k": {"type": "integer", "description": "Max results to return.", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "api_fetch",
        "description": ("Call an API endpoint by its full URL (from api_search results). "
                        "method: GET/POST/PUT/PATCH/DELETE. params/body: JSON strings."),
        "parameters": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "description": "HTTP method."},
                "url": {"type": "string", "description": "Full endpoint URL."},
                "params": {"type": "string", "description": "Query parameters as a JSON object string."},
                "body": {"type": "string", "description": "Request body as a JSON object string."},
            },
            "required": ["method", "url"],
        },
    },
    {
        "name": "base64_encode",
        "description": "Encode text to base64url (required by Gmail API body fields).",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Text to encode."}},
            "required": ["text"],
        },
    },
]


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def build_tools_openai() -> list[dict]:
    return json.loads(canonical_json(
        [{"type": "function", "function": d} for d in _TOOL_DEFS]))


def build_tools_gemini() -> list[dict]:
    return json.loads(canonical_json(_TOOL_DEFS))


def build_tools_responses() -> list[dict]:
    # OpenAI Responses API flattens the function object (no nested "function").
    return json.loads(canonical_json(
        [{"type": "function", "name": d["name"], "description": d["description"],
          "parameters": d["parameters"]} for d in _TOOL_DEFS]))


def build_tools_anthropic() -> list[dict]:
    # Anthropic caching is explicit: the breakpoint on the last tool caches the
    # whole tools prefix (tools render before system and messages).
    tools = json.loads(canonical_json(
        [{"name": d["name"], "description": d["description"], "input_schema": d["parameters"]}
         for d in _TOOL_DEFS]))
    tools[-1]["cache_control"] = {"type": "ephemeral"}
    return tools


class InfraError(Exception):
    def __init__(self, kind: str, msg: str, retry_after: float | None = None,
                 retryable: bool = True):
        super().__init__(msg)
        self.kind = kind                # infra:rate_limit | infra:model_unavailable | infra:harness_crash
        self.retry_after = retry_after
        self.retryable = retryable      # False: retrying can never help (e.g. missing key)


class EpisodeTimeout(Exception):
    pass


@dataclass
class ArmResult:
    termination: str = "completed"
    error: str | None = None
    turns: int = 0
    tool_calls: int = 0
    tokens_prompt: int = 0
    tokens_cached: int = 0
    tokens_cache_write: int = 0     # Anthropic cache-creation tokens (billed 1.25x)
    tokens_output: int = 0
    cost_usd: float = 0.0
    flags: list[str] = field(default_factory=list)
    turn_log: list[dict] = field(default_factory=list)
    final_text: str | None = None
    phases: dict = field(default_factory=dict)          # M2 arms: authoring/execution split
    gate_refusals: list[dict] = field(default_factory=list)


def _exec_tool(ep: Episode, name: str, args: dict) -> str:
    try:
        if name == "api_search":
            return ep.api_search(args["query"], int(args.get("top_k") or 5))
        if name == "api_fetch":
            params, body = args.get("params"), args.get("body")
            if isinstance(params, dict):
                params = json.dumps(params)
            if isinstance(body, dict):
                body = json.dumps(body)
            return ep.api_fetch(args["method"], args["url"], params=params, body=body)
        if name == "base64_encode":
            return ep.base64_encode(args["text"])
        return json.dumps({"error": f"unknown tool {name}"})
    except EvidenceWriteError:
        # A missing durable observation is a harness failure, not an application
        # error to send back to the model and continue spending through.
        raise
    except Exception as e:
        return json.dumps({"error": str(e)})


class _OpenAIAdapter:
    """Chat-completions transport for glm/kimi/fireworks (and the test mock)."""

    def __init__(self, provider: Provider, tools: list[dict], timeout: float = 120.0):
        import openai
        self._openai = openai
        key = providers.api_key(provider)
        if not key:
            raise InfraError("infra:harness_crash", f"{provider.key_env} not set",
                             retryable=False)
        self.provider = provider
        self.tools = tools
        self.client = openai.OpenAI(api_key=key, base_url=provider.base_url,
                                    timeout=timeout, max_retries=0)

    def start(self, system: str, brief: str) -> list[dict]:
        return [{"role": "system", "content": system}, {"role": "user", "content": brief}]

    def turn(self, messages: list[dict], timeout: float | None = None) -> dict:
        kwargs = {"timeout": timeout} if timeout is not None else {}
        try:
            raw = self.client.chat.completions.with_raw_response.create(
                model=self.provider.model_id, messages=messages, tools=self.tools, **kwargs)
            resp = raw.parse()
            headers = dict(raw.headers)
        except self._openai.RateLimitError as e:
            raise InfraError("infra:rate_limit", str(e), _retry_after(e)) from e
        except self._openai.NotFoundError as e:
            raise InfraError("infra:model_unavailable", str(e)) from e
        except self._openai.APIStatusError as e:
            kind = "infra:model_unavailable" if e.status_code in (502, 503) else "infra:harness_crash"
            raise InfraError(kind, str(e), _retry_after(e)) from e
        except self._openai.APIConnectionError as e:
            raise InfraError("infra:harness_crash", str(e)) from e

        if not resp.choices or resp.choices[0].message is None:
            # Provider anomaly, not agent behavior: retryable infra.
            raise InfraError("infra:model_unavailable", "provider returned empty choices")
        msg = resp.choices[0].message
        usage = resp.usage.model_dump() if resp.usage else {}
        cached, source = providers.extract_cached_tokens(usage, headers, self.provider)
        calls = []
        for tc in (msg.tool_calls or []):
            entry = {"id": tc.id, "name": tc.function.name, "args": {}}
            # Malformed arguments (truncation, model slip) go back to the model
            # as a tool error it can recover from — never crash the episode.
            try:
                parsed = json.loads(tc.function.arguments or "{}")
                if isinstance(parsed, dict):
                    entry["args"] = parsed
                else:
                    entry["parse_error"] = f"arguments must be a JSON object, got {type(parsed).__name__}"
            except json.JSONDecodeError as e:
                entry["parse_error"] = str(e)
            calls.append(entry)
        messages.append(json.loads(msg.model_dump_json(exclude_none=True)))
        return {"tool_calls": calls, "text": msg.content,
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "output_tokens": int(usage.get("completion_tokens") or 0),
                "cached_tokens": cached, "cache_source": source}

    def append_tool_result(self, messages: list[dict], call: dict, result: str) -> None:
        messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})


class _GeminiAdapter:
    """Native google-genai transport; implicit caching, usageMetadata reporting."""

    def __init__(self, provider: Provider, tools: list[dict], timeout: float = 120.0):
        from google import genai
        from google.genai import types, errors
        key = providers.api_key(provider)
        if not key:
            raise InfraError("infra:harness_crash", f"{provider.key_env} not set",
                             retryable=False)
        self.provider = provider
        self.types, self.errors = types, errors
        self.client = genai.Client(api_key=key,
                                   http_options=types.HttpOptions(timeout=int(timeout * 1000)))
        self.config = types.GenerateContentConfig(
            system_instruction=None,  # set in start(); fixed thereafter
            tools=[types.Tool(function_declarations=[
                types.FunctionDeclaration(name=d["name"], description=d["description"],
                                          parameters_json_schema=d["parameters"])
                for d in tools])])

    def start(self, system: str, brief: str) -> list:
        self.config.system_instruction = system
        return [self.types.Content(role="user", parts=[self.types.Part(text=brief)])]

    def turn(self, contents: list, timeout: float | None = None) -> dict:
        # (Gemini client timeout is fixed at construction; the loop's deadline
        # check still bounds the episode.)
        try:
            resp = self.client.models.generate_content(
                model=self.provider.model_id, contents=contents, config=self.config)
        except self.errors.APIError as e:
            code = getattr(e, "code", None)
            if code == 429:
                raise InfraError("infra:rate_limit", str(e)) from e
            if code in (404, 502, 503):
                raise InfraError("infra:model_unavailable", str(e)) from e
            raise InfraError("infra:harness_crash", str(e)) from e

        meta = resp.usage_metadata
        usage = {"cached_content_token_count": getattr(meta, "cached_content_token_count", None)}
        cached, source = providers.extract_cached_tokens(usage)
        candidate = resp.candidates[0] if resp.candidates else None
        calls, text = [], None
        if candidate and candidate.content:
            contents.append(candidate.content)
            for i, part in enumerate(candidate.content.parts or []):
                if part.function_call:
                    calls.append({"id": f"fc{i}", "name": part.function_call.name,
                                  "args": dict(part.function_call.args or {})})
                elif part.text:
                    text = (text or "") + part.text
        return {"tool_calls": calls, "text": text,
                "prompt_tokens": int(getattr(meta, "prompt_token_count", 0) or 0),
                "output_tokens": int(getattr(meta, "candidates_token_count", 0) or 0),
                "cached_tokens": cached, "cache_source": source}

    def append_tool_result(self, contents: list, call: dict, result: str) -> None:
        contents.append(self.types.Content(role="user", parts=[
            self.types.Part.from_function_response(name=call["name"],
                                                   response={"result": result})]))


class _OpenAIResponsesAdapter:
    """OpenAI Responses API transport. Reasoning models (gpt-5.6-*) refuse
    function tools with reasoning on the chat-completions endpoint, and turning
    reasoning off would be an unfair control against Opus at xhigh. History is
    the append-only `input` list: every output item (reasoning + calls) is
    echoed back, then function_call_output items are appended."""

    def __init__(self, provider: Provider, tools: list[dict], timeout: float = 120.0):
        import openai
        self._openai = openai
        key = providers.api_key(provider)
        if not key:
            raise InfraError("infra:harness_crash", f"{provider.key_env} not set",
                             retryable=False)
        self.provider = provider
        self.tools = tools
        self.client = openai.OpenAI(api_key=key, base_url=provider.base_url,
                                    timeout=timeout, max_retries=0)
        self.effort = os.environ.get("WB_OPENAI_EFFORT") or provider.effort
        self.instructions = ""

    def start(self, system: str, brief: str) -> list[dict]:
        self.instructions = system
        return [{"role": "user", "content": brief}]

    def turn(self, items: list[dict], timeout: float | None = None) -> dict:
        o = self._openai
        client = self.client.with_options(timeout=timeout) if timeout is not None else self.client
        try:
            resp = client.responses.create(
                model=self.provider.model_id, instructions=self.instructions,
                input=items, tools=self.tools, reasoning={"effort": self.effort},
                max_output_tokens=16000)
        except o.RateLimitError as e:
            raise InfraError("infra:rate_limit", str(e), _retry_after(e)) from e
        except o.NotFoundError as e:
            raise InfraError("infra:model_unavailable", str(e)) from e
        except o.APIStatusError as e:
            kind = "infra:model_unavailable" if e.status_code in (502, 503) else "infra:harness_crash"
            raise InfraError(kind, str(e), _retry_after(e)) from e
        except o.APIConnectionError as e:
            raise InfraError("infra:harness_crash", str(e)) from e

        u = resp.usage
        det = getattr(u, "input_tokens_details", None)
        cached = int(getattr(det, "cached_tokens", 0) or 0)
        calls, text = [], None
        for item in resp.output:
            items.append(json.loads(item.model_dump_json(exclude_none=True)))
            if item.type == "function_call":
                entry = {"id": item.call_id, "name": item.name, "args": {}}
                try:
                    parsed = json.loads(item.arguments or "{}")
                    if isinstance(parsed, dict):
                        entry["args"] = parsed
                    else:
                        entry["parse_error"] = f"arguments must be a JSON object, got {type(parsed).__name__}"
                except json.JSONDecodeError as e:
                    entry["parse_error"] = str(e)
                calls.append(entry)
            elif item.type == "message":
                for part in item.content or []:
                    if getattr(part, "type", "") == "output_text":
                        text = (text or "") + part.text
        return {"tool_calls": calls, "text": text,
                "prompt_tokens": int(u.input_tokens or 0), "output_tokens": int(u.output_tokens or 0),
                "cached_tokens": cached, "cache_source": "usage.input_tokens_details.cached_tokens"}

    def append_tool_result(self, items: list[dict], call: dict, result: str) -> None:
        items.append({"type": "function_call_output", "call_id": call["id"], "output": result})


class _AnthropicAdapter:
    """Native Anthropic Messages transport. Prompt caching is explicit here:
    one breakpoint on the tools prefix (build_tools_anthropic) and one on the
    system prompt; the append-only history then rides on the cached prefix.
    Thinking blocks are echoed back untouched (same model, required)."""

    def __init__(self, provider: Provider, tools: list[dict], timeout: float = 120.0):
        import anthropic
        self._anthropic = anthropic
        key = providers.api_key(provider)
        if not key:
            raise InfraError("infra:harness_crash", f"{provider.key_env} not set",
                             retryable=False)
        self.provider = provider
        self.tools = tools
        self.client = anthropic.Anthropic(api_key=key, timeout=timeout, max_retries=0)
        # The model file sets the effort (Monarch's brain runs xhigh); the env
        # override is for ablations.
        self.effort = os.environ.get("WB_ANTHROPIC_EFFORT") or provider.effort
        self.system: list[dict] = []

    def start(self, system: str, brief: str) -> list[dict]:
        self.system = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        return [{"role": "user", "content": brief}]

    def turn(self, messages: list[dict], timeout: float | None = None) -> dict:
        a = self._anthropic
        client = self.client.with_options(timeout=timeout) if timeout is not None else self.client
        try:
            # Top-level cache_control caches the last cacheable block, i.e. the
            # whole conversation so far. The tools+system prefix alone (~800
            # tokens) is under Opus 4.8's 1024-token cache minimum, so the
            # per-block breakpoints on tools/system only pay off once history
            # is appended; this one makes every turn cache the previous turn.
            resp = client.messages.create(
                model=self.provider.model_id, max_tokens=16000,
                system=self.system, tools=self.tools, messages=messages,
                cache_control={"type": "ephemeral"},
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort})
        except a.RateLimitError as e:
            raise InfraError("infra:rate_limit", str(e), _retry_after(e)) from e
        except a.NotFoundError as e:
            raise InfraError("infra:model_unavailable", str(e)) from e
        except a.APIStatusError as e:
            kind = "infra:model_unavailable" if e.status_code in (502, 503, 529) else "infra:harness_crash"
            raise InfraError(kind, str(e), _retry_after(e)) from e
        except a.APIConnectionError as e:
            raise InfraError("infra:harness_crash", str(e)) from e

        u = resp.usage
        cached = int(u.cache_read_input_tokens or 0)
        cache_write = int(u.cache_creation_input_tokens or 0)
        prompt = int(u.input_tokens or 0) + cached + cache_write
        # Echo the full content (thinking + text + tool_use) so the next request
        # is a byte-stable extension of this one.
        messages.append({"role": "assistant",
                         "content": [b.model_dump(exclude_none=True) for b in resp.content]})
        calls, text = [], None
        for b in resp.content:
            if b.type == "tool_use":
                entry = {"id": b.id, "name": b.name, "args": {}}
                if isinstance(b.input, dict):
                    entry["args"] = b.input
                else:
                    entry["parse_error"] = f"tool input must be an object, got {type(b.input).__name__}"
                calls.append(entry)
            elif b.type == "text":
                text = (text or "") + b.text
        if resp.stop_reason == "refusal":
            calls = []   # treated as a final answer; the grader decides the verdict
        return {"tool_calls": calls, "text": text,
                "prompt_tokens": prompt, "output_tokens": int(u.output_tokens or 0),
                "cached_tokens": cached, "cache_write_tokens": cache_write,
                "cache_source": "usage.cache_read_input_tokens"}

    def append_tool_result(self, messages: list[dict], call: dict, result: str) -> None:
        # All results for one assistant turn must land in ONE user message;
        # the loop calls this once per tool call, so merge into the open one.
        block = {"type": "tool_result", "tool_use_id": call["id"], "content": result}
        if messages and messages[-1]["role"] == "user" and isinstance(messages[-1]["content"], list):
            messages[-1]["content"].append(block)
        else:
            messages.append({"role": "user", "content": [block]})


def _json_messages(messages: list) -> list:
    """Normalize SDK messages without flattening their structured contents."""
    def encode(value):
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json", exclude_none=True)
        raise TypeError(f"unsupported message type: {type(value).__name__}")
    return json.loads(json.dumps(messages, default=encode))


class ApiLoopArm:
    message_evidence = "normalized"  # observable messages; not raw provider/private reasoning
    """One arm instance per (provider, run); tools serialized once, reused verbatim."""

    def __init__(self, provider_key: str, request_timeout: float = 120.0):
        self.provider = providers.get(provider_key)
        self.name = f"bare/api/{provider_key}"
        self._tools_openai = build_tools_openai()
        self._tools_gemini = build_tools_gemini()
        self._tools_anthropic = build_tools_anthropic()
        self._tools_responses = build_tools_responses()
        self._request_timeout = request_timeout

    def _adapter(self):
        if self.provider.adapter == "gemini":
            return _GeminiAdapter(self.provider, self._tools_gemini, self._request_timeout)
        if self.provider.adapter == "openai_responses":
            return _OpenAIResponsesAdapter(self.provider, self._tools_responses, self._request_timeout)
        if self.provider.adapter == "anthropic":
            return _AnthropicAdapter(self.provider, self._tools_anthropic, self._request_timeout)
        return _OpenAIAdapter(self.provider, self._tools_openai, self._request_timeout)

    def run(self, ep: Episode, deadline: float | None = None) -> ArmResult:
        res = ArmResult()
        try:
            return self._run(ep, deadline, res)
        except EvidenceWriteError as exc:
            # The response may already have incurred cost before its journal
            # failed. Preserve those observed tokens and stop without retry:
            # a later successful write cannot make this trajectory complete.
            res.flags.append("evidence_incomplete")
            res.termination = "infra:harness_crash"
            res.error = str(exc)
            res.cost_usd = providers.cost_usd(self.provider, res.tokens_prompt,
                                              res.tokens_cached, res.tokens_output,
                                              res.tokens_cache_write)
            failed = InfraError("infra:harness_crash", str(exc), retryable=False)
            failed.partial = res
            raise failed from exc

    def _run(self, ep: Episode, deadline: float | None, res: ArmResult) -> ArmResult:
        system = ep.task["prompt"][0]["content"]
        brief = ep.task["prompt"][1]["content"]
        adapter = self._adapter()
        messages = adapter.start(system, brief)
        prev_prompt_tokens: int | None = None
        saw_cache_source = degraded_flagged = False

        for turn_i in range(MAX_TOOL_TURNS):
            if deadline is not None and time.monotonic() > deadline:
                # Timeout is a RESULT, not an exception: the tokens already
                # burned must reach the row, not evaporate with a raise.
                res.termination = "timeout"
                res.error = f"deadline hit after {turn_i} turns"
                break
            # Per-request timeout never exceeds the episode's remaining budget,
            # so a stalled provider can't overrun ARM_RUN's deadline by 120s.
            budget = None if deadline is None else max(deadline - time.monotonic(), 1.0)
            entry = {"turn": turn_i, "request": {"messages": _json_messages(messages)},
                     "started_monotonic": time.monotonic(), "tool_results": []}
            res.turn_log.append(entry)
            ep.record_agent_event({"type": "agent_request", **entry})
            try:
                t = adapter.turn(messages,
                                 timeout=None if budget is None else min(self._request_timeout, budget))
            except InfraError as e:
                entry.update(status="error", error=str(e), finished_monotonic=time.monotonic())
                ep.record_agent_event({"type": "agent_error", **entry})
                if deadline is not None and time.monotonic() > deadline:
                    # The request died because the episode budget expired —
                    # that's a timeout verdict, not an infra retry.
                    res.termination = "timeout"
                    res.error = f"request cut at episode deadline: {e}"
                    break
                # Spend so far rides out on the exception for the orchestrator
                # to accumulate across attempts.
                res.cost_usd = providers.cost_usd(self.provider, res.tokens_prompt,
                                                  res.tokens_cached, res.tokens_output,
                                                  res.tokens_cache_write)
                e.partial = res
                raise
            res.turns += 1
            res.tokens_prompt += t["prompt_tokens"]
            res.tokens_cached += t["cached_tokens"]
            res.tokens_cache_write += t.get("cache_write_tokens", 0)
            res.tokens_output += t["output_tokens"]
            entry.update({"prompt_tokens": t["prompt_tokens"],
                          "cached_tokens": t["cached_tokens"],
                          "output_tokens": t["output_tokens"],
                          "cache_source": t["cache_source"],
                          "tool_calls": [c["name"] for c in t["tool_calls"]],
                          "response": {"text": t["text"], "tool_calls": _json_messages(t["tool_calls"])},
                          "status": "completed", "finished_monotonic": time.monotonic()})
            ep.record_agent_event({"type": "agent_response", **entry})
            saw_cache_source = saw_cache_source or t["cache_source"] is not None
            if t["cached_tokens"] > t["prompt_tokens"] and "cache_overreport" not in res.flags:
                res.flags.append("cache_overreport")   # provider bug; cost math clamps
            # Regression assertion: prefix breakage shows up as the cache not
            # covering the previous turn's prompt. Only meaningful once a prior
            # turn exists to have populated the cache (turn 3 on, 0-indexed >= 2).
            if (turn_i >= 2 and t["cache_source"] is not None and prev_prompt_tokens
                    and t["cached_tokens"] < 0.8 * prev_prompt_tokens and not degraded_flagged):
                res.flags.append(f"cache_degraded@msg={len(messages) - 1}")
                degraded_flagged = True
            prev_prompt_tokens = t["prompt_tokens"]

            if not t["tool_calls"]:
                res.final_text = t["text"]
                break
            for call in t["tool_calls"]:
                if call.get("parse_error"):
                    result = json.dumps({"error": "tool call arguments were not valid JSON: "
                                                  + call["parse_error"]})
                else:
                    result = _exec_tool(ep, call["name"], call["args"])
                truncated = len(result) > MAX_TOOL_RESULT_CHARS
                if truncated:
                    result = result[:MAX_TOOL_RESULT_CHARS] + " ...[truncated by harness]"
                res.tool_calls += 1
                entry["tool_results"].append({"call_id": call["id"], "name": call["name"],
                                              "content": result, "truncated": truncated})
                adapter.append_tool_result(messages, call, result)
                ep.record_agent_event({"type": "tool_result_delivered", "turn": turn_i,
                                       **entry["tool_results"][-1]})
        else:
            res.flags.append("turn_budget_exhausted")
            res.termination = "agent_error"
            res.error = "tool turn budget exhausted without a final response"

        # Providers that omit the cache field on uncached turns (Gemini) must
        # not be flagged absent: only flag when NO turn ever reported one.
        if res.turns and not saw_cache_source:
            res.flags.append("cache_reporting=absent")
        res.cost_usd = providers.cost_usd(self.provider, res.tokens_prompt,
                                          res.tokens_cached, res.tokens_output,
                                          res.tokens_cache_write)
        return res


def _retry_after(e) -> float | None:
    try:
        v = e.response.headers.get("Retry-After")
        return float(v) if v is not None else None
    except Exception:
        return None
