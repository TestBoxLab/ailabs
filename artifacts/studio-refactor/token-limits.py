from pathlib import Path
p=Path('monarch-benchmark/workflowbench/wb_studio/runtime.py');s=p.read_text(encoding='utf8')
s=s.replace('{"concurrency", "requests_per_minute"}', '{"concurrency", "requests_per_minute", "tokens_per_minute"}')
s=s.replace('            positive_int(limit.get("requests_per_minute", 30), "Requests per minute", 100000)', '            positive_int(limit.get("requests_per_minute", 30), "Requests per minute", 100000)\n            if "tokens_per_minute" in limit:\n                positive_int(limit["tokens_per_minute"], "Tokens per minute", 1000000000)')
s=s.replace('def provider(self, name, *, timeout=None, cancel=None):', 'def provider(self, name, *, timeout=None, cancel=None, tokens=0):')
s=s.replace('        concurrency, rpm = limit.get("concurrency", 2), limit.get("requests_per_minute", 30)', '        concurrency, rpm = limit.get("concurrency", 2), limit.get("requests_per_minute", 30)\n        tpm = limit.get("tokens_per_minute")\n        if type(tokens) is not int or tokens < 0:\n            raise ValueError("Token reservation must be a nonnegative integer")\n        if tpm is not None and tokens > tpm:\n            raise GatewayError("This request exceeds the configured token-per-minute capacity; reduce its context or raise the operator limit", kind="infra:rate_limit")')
s=s.replace('{"active": 0, "starts": deque()}', '{"active": 0, "starts": deque(), "token_starts": deque()}')
s=s.replace('                if cancel is not None and cancel.is_set():', '                while state["token_starts"] and state["token_starts"][0][0] <= now - 60:\n                    state["token_starts"].popleft()\n                if cancel is not None and cancel.is_set():')
s=s.replace('if state["active"] < concurrency and len(state["starts"]) < rpm:', 'if state["active"] < concurrency and len(state["starts"]) < rpm and (tpm is None or sum(n for _, n in state["token_starts"]) + tokens <= tpm):')
s=s.replace('                    state["starts"].append(now)', '                    state["starts"].append(now)\n                    state["token_starts"].append((now,tokens))')
s=s.replace('"requests_per_minute": self.limits.get(name, {}).get("requests_per_minute", 30),', '"requests_per_minute": self.limits.get(name, {}).get("requests_per_minute", 30),\n                                   "tokens_per_minute": self.limits.get(name, {}).get("tokens_per_minute"),')
s=s.replace('token quotas are not inferred.', 'optional token quotas use conservative request bounds and are not refunded from unverified usage.')
s=s.replace('        with self.runtime.provider(self.provider, timeout=kwargs.get("timeout"), cancel=cancel) as remaining:', '''        # Text-only tool calls: UTF-8 byte count safely overestimates tokenized input.
        # Include schema/system bytes and maximum completion/thinking allowance.
        from wb_studio.gateways import OUTPUT_CEILING
        from wb_studio.paid import THINKING_CEILING
        family = getattr(self.gateway, "family", "gemini")
        output = OUTPUT_CEILING.get(family, THINKING_CEILING + 4096)
        tokens = len(json.dumps([getattr(self.gateway,"system",""), messages, getattr(self.gateway,"tools",[])], ensure_ascii=False, default=str).encode()) + output + 1024
        with self.runtime.provider(self.provider, timeout=kwargs.get("timeout"), cancel=cancel, tokens=tokens) as remaining:''')
p.write_text(s,encoding='utf8')
