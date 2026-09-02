"""In-tests mock OpenAI-compatible chat-completions server (stdlib only).

Stateless per request: if the conversation contains fewer than n_tool_turns
tool results it returns a tool call, else a final message. Behavior knobs are
attributes on the server object (fail_requests, delay_s, cache_mode).
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class MockOpenAIServer:
    def __init__(self):
        self.request_count = 0
        self.fail_requests: set[int] = set()   # 1-indexed request numbers -> 429
        self.delay_s = 0.0
        self.cache_mode = "good"               # good | degraded | absent | absent_first | overreport
        self.n_tool_turns = 1
        self.retry_after_header = True         # False: 429 without Retry-After (backoff path)
        self.bad_args_requests: set[int] = set()      # tool call with unparseable arguments
        self.empty_choices_requests: set[int] = set() # provider anomaly: choices=[]
        self.override_tool_call: dict | None = None   # {"name":..., "args":...} for tool turns
        self._lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                with outer._lock:
                    outer.request_count += 1
                    n = outer.request_count
                if outer.delay_s:
                    time.sleep(outer.delay_s)
                if n in outer.fail_requests:
                    payload = json.dumps({"error": {"message": "rate limited", "type": "rate_limit_error"}}).encode()
                    self.send_response(429)
                    if outer.retry_after_header:
                        self.send_header("Retry-After", "0")
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                self._reply(outer.build_response(body["messages"], n))

            def _reply(self, obj):
                payload = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}/v1"
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()

    def build_response(self, messages: list[dict], n: int = 0) -> dict:
        tool_results = sum(1 for m in messages if m.get("role") == "tool")
        turn_index = tool_results  # 0-based model turn within the conversation
        prompt_tokens = 500 + 100 * len(messages)
        if self.cache_mode == "overreport" and turn_index >= 1:
            cached = prompt_tokens * 2
        elif turn_index == 0:
            cached = 0
        elif self.cache_mode == "degraded" and turn_index >= 2:
            cached = 0
        else:
            cached = int(prompt_tokens * 0.95)
        usage = {"prompt_tokens": prompt_tokens, "completion_tokens": 20,
                 "total_tokens": prompt_tokens + 20}
        # absent_first mimics Gemini: the cache field is simply omitted on
        # uncached turns and appears once something is cached.
        omit = self.cache_mode == "absent" or (
            self.cache_mode == "absent_first" and turn_index == 0)
        if not omit:
            usage["prompt_tokens_details"] = {"cached_tokens": cached}
        if n in self.empty_choices_requests:
            return {"id": "chatcmpl-mock", "object": "chat.completion", "created": 0,
                    "model": "mock-1", "choices": [], "usage": usage}
        if tool_results < self.n_tool_turns:
            if n in self.bad_args_requests:
                arguments = '{"query": "salesforce upd'      # truncated mid-string
            elif self.override_tool_call:
                arguments = json.dumps(self.override_tool_call["args"])
            else:
                arguments = json.dumps({"query": "salesforce update"})
            name = (self.override_tool_call or {}).get("name", "api_search")
            message = {"role": "assistant", "content": None, "tool_calls": [{
                "id": f"call_{tool_results}", "type": "function",
                "function": {"name": name, "arguments": arguments}}]}
            finish = "tool_calls"
        else:
            message = {"role": "assistant", "content": "done"}
            finish = "stop"
        return {"id": "chatcmpl-mock", "object": "chat.completion", "created": 0,
                "model": "mock-1",
                "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                "usage": usage}

    def shutdown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
