"""Versioned configuration artifacts; no evaluated code or paid calls run here."""
from __future__ import annotations

import base64
import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import urllib.error
import urllib.request

import yaml

REPOSITORY = "TestBoxLab/ailabls-benchmark-config"
MAX_FILE = 1_048_576
MAX_TREE = 8_388_608
SHA = re.compile(r"[0-9a-f]{40}")


class RepositoryError(ValueError):
    status = 503


class Conflict(RepositoryError):
    status = 409


def safe_path(value):
    if not isinstance(value, str) or not re.fullmatch(r"config/[A-Za-z0-9_./-]+", value):
        raise ValueError("Expected a config file path")
    path = PurePosixPath(value)
    if any(p in (".", "..") for p in value.split("/")) or str(path) != value:
        raise ValueError("Config paths cannot escape their directory")
    allowed = (len(path.parts) == 3 and path.parts[1] in ("models", "harnesses", "plans", "products")
               and path.suffix == ".yaml") or value in ("config/README.md", "config/side-effects.yaml")
    if not allowed:
        raise ValueError("Unsupported config file path")
    return value


def _texts(records):
    if not isinstance(records, list) or len(records) > 512:
        raise ValueError("Expected at most 512 configuration files")
    result = {}
    for row in records:
        path = safe_path(row["path"])
        text = row["text"]
        if path in result or not isinstance(text, str) or len(text.encode()) > MAX_FILE:
            raise ValueError("Duplicate, invalid or oversized configuration file")
        if hashlib.sha256(text.encode()).hexdigest() != row["sha256"]:
            raise ValueError("Configuration artifact hash mismatch")
        result[path] = text
    if sum(len(t.encode()) for t in result.values()) > MAX_TREE:
        raise ValueError("Configuration tree is too large")
    return result


def _records(files):
    return [{"path": path, "text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()}
            for path, text in sorted(files.items())]


def cache_path():
    return Path(os.environ.get("WB_CONFIG_CACHE") or
                str(Path(os.environ.get("STUDIO_DATA_DIR") or Path.home() / ".cache" / "workflowbench") / "config-revisions"))


def restore_snapshot(source, cache_dir=None):
    """Restore evidence without network access, verifying bytes before activation."""
    if not isinstance(source, dict) or not SHA.fullmatch(str(source.get("commit", ""))):
        raise ValueError("Expected an immutable configuration commit")
    repository = source.get("repository", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid configuration repository")
    texts = _texts(source["files"])
    parent = Path(cache_dir or cache_path()) / hashlib.sha256(repository.encode()).hexdigest()[:16]
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / source["commit"]
    manifest = {k: source[k] for k in ("repository", "branch", "commit", "files")}
    if target.exists():
        saved = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        if saved != manifest:
            raise ValueError("Immutable configuration cache manifest changed")
        for name, text in texts.items():
            file = target / name
            if file.is_symlink() or file.read_bytes() != text.encode():
                raise ValueError("Immutable configuration cache content changed")
    else:
        with tempfile.TemporaryDirectory(prefix="incoming-", dir=parent) as temp:
            incoming = Path(temp) / "revision"
            incoming.mkdir()
            for name, text in texts.items():
                file = incoming / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(text.encode())
            (incoming / "manifest.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
            try:
                incoming.rename(target)
            except OSError:
                if not target.exists():
                    raise
                return restore_snapshot(source, cache_dir)
    return {**manifest, "directory": str(target)}


def validate_files(files):
    """Existing loaders validate structure; runtime readiness is checked at preview."""
    from wb_orchestrator import config as c
    errors = []
    models, harnesses, plans, products = {}, {}, {}, {}
    if not isinstance(files, dict) or len(files) > 512:
        return ["Expected a configuration file mapping"]
    if not files:
        return ["Configuration tree cannot be empty"]
    if any(not isinstance(t, str) for t in files.values()) or sum(len(t.encode()) for t in files.values()) > MAX_TREE:
        return ["Configuration tree is invalid or too large"]
    with tempfile.TemporaryDirectory(prefix="wb-config-validate-") as temp:
        root = Path(temp)
        data = {}
        for name, text in files.items():
            try:
                safe_path(name)
                if not isinstance(text, str) or len(text.encode()) > MAX_FILE:
                    raise ValueError("Invalid or oversized content")
                if re.search(r"(?:sk-(?:ant-|lf-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{25,}|-----BEGIN .*PRIVATE KEY)", text):
                    raise ValueError("Secret values cannot be stored in configuration")
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(text.encode())
                if file.suffix != ".yaml":
                    continue
                depth = 0
                for event in yaml.parse(text):
                    if isinstance(event, yaml.events.AliasEvent):
                        raise ValueError("YAML aliases are not supported")
                    if isinstance(event, (yaml.events.MappingStartEvent, yaml.events.SequenceStartEvent)):
                        depth += 1
                    if depth > 30:
                        raise ValueError("YAML nesting is too deep")
                    if isinstance(event, (yaml.events.MappingEndEvent, yaml.events.SequenceEndEvent)):
                        depth -= 1
                data[name] = yaml.safe_load(text)
                group = file.parent.name
                if name == "config/side-effects.yaml":
                    c.load_side_effects(file)
                elif group == "models":
                    models[file.stem] = c.load_price_table(file) if c.is_price_table(file) else c.load_model(file)
                elif group == "harnesses":
                    harnesses[file.stem] = c.load_harness(file)
                elif group == "plans":
                    plans[file.stem] = c.load_plan(file)
                elif group == "products" and "." not in file.stem:
                    products[file.stem] = c.load_product(file)
                elif group == "products" and not file.name.endswith((".monarch-kb.yaml", ".monarch-recipes.yaml", ".knowledge-map.yaml")):
                    raise ValueError("Unknown supporting product file")
            except (ValueError, c.ConfigError, yaml.YAMLError, TypeError) as exc:
                errors.append(f"{name}: {exc}")
        for name, product in products.items():
            if product.side_effects not in files:
                errors.append(f"config/products/{name}.yaml: missing {product.side_effects}")
        for name, h in harnesses.items():
            if h.kind == "monarch" and not isinstance(models.get(h.price_table), c.PriceTable):
                errors.append(f"config/harnesses/{name}.yaml: missing price table {h.price_table}")
        for name, p in plans.items():
            names = []
            for spec in p.competitors:
                names.append(f"{spec.model}/{spec.harness}" if spec.model else spec.harness)
                h, m = harnesses.get(spec.harness), models.get(spec.model)
                if h is None:
                    errors.append(f"config/plans/{name}.yaml: missing harness {spec.harness}")
                elif spec.model and (not isinstance(m, c.Model) or h.accepts == "none" or m.provider not in h.accepts):
                    errors.append(f"config/plans/{name}.yaml: incompatible or missing model {spec.model}")
                elif not spec.model and h.accepts != "none":
                    errors.append(f"config/plans/{name}.yaml: harness {spec.harness} needs a model")
            if p.baseline not in names or len(set(names)) != len(names):
                errors.append(f"config/plans/{name}.yaml: invalid baseline or duplicate competitors")
        for name, value in data.items():
            if not name.startswith("config/products/") or "." not in Path(name).stem:
                continue
            try:
                product = products[Path(name).stem.split(".")[0]]
                if name.endswith(".monarch-kb.yaml"):
                    c.load_monarch_kb(root / name, product)
                elif name.endswith(".monarch-recipes.yaml"):
                    c.load_monarch_recipes(root / name, product.name, list(value.get("recipes", {})) + list(value.get("missing", {})))
                elif not isinstance(value, dict) or value.get("product") != product.name or not isinstance(value.get("rows"), dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value["rows"].items()):
                    raise ValueError("Expected a product knowledge map with string rows")
            except (ValueError, c.ConfigError, KeyError, TypeError, AttributeError) as exc:
                errors.append(f"{name}: {exc}")
    return errors


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RepositoryError("Repository redirect refused")


class Repository:
    def __init__(self, repository=REPOSITORY, token=None, cache_dir=None, *, request=None):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("Invalid configuration repository")
        self.repository, self.token = repository, token
        self.cache_dir = Path(cache_dir or cache_path())
        self.request = request or self._request

    @classmethod
    def from_env(cls, cache_dir=None, env=None):
        env = os.environ if env is None else env
        repository = env.get("WB_CONFIG_REPOSITORY")
        if not repository:
            return None
        token = env.get("WB_CONFIG_GITHUB_TOKEN")
        if not token and not env.get("STUDIO_DATA_DIR"):
            try:
                result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10)
                token = result.stdout.strip() if result.returncode == 0 else None
            except (OSError, subprocess.TimeoutExpired):
                pass
        return cls(repository, token, cache_dir or env.get("WB_CONFIG_CACHE"))

    def _request(self, method, path, body=None):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "WorkflowBench"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(f"https://api.github.com/repos/{self.repository}/{path}",
                                         data=json.dumps(body).encode() if body is not None else None,
                                         headers=headers, method=method)
        try:
            with urllib.request.build_opener(_NoRedirect()).open(request, timeout=25) as response:
                raw = response.read(MAX_TREE * 2 + 1)
                if len(raw) > MAX_TREE * 2:
                    raise RepositoryError("Repository response is too large")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            if exc.code in (409, 422):
                raise Conflict("Repository changed or GitHub refused the commit; refresh and review") from None
            raise RepositoryError(f"Repository request failed (HTTP {exc.code}); check repository access") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            if isinstance(exc, RepositoryError):
                raise
            raise RepositoryError("Repository request failed; saved revisions and drafts are retained") from None

    def head(self):
        value = self.request("GET", "git/ref/heads/main")["object"]["sha"]
        if not SHA.fullmatch(value):
            raise RepositoryError("Repository returned an invalid commit")
        return value

    def snapshot(self, commit=None):
        commit = commit or self.head()
        if not isinstance(commit, str) or not SHA.fullmatch(commit):
            raise ValueError("Expected a full immutable configuration commit")
        folder = self.cache_dir / hashlib.sha256(self.repository.encode()).hexdigest()[:16] / commit
        if folder.exists():
            saved = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            if saved.get("commit") != commit or saved.get("repository") != self.repository:
                raise ValueError("Immutable configuration cache identity changed")
            return restore_snapshot(saved, self.cache_dir)
        tree = self.request("GET", "git/trees/" + commit + "?recursive=1")
        if tree.get("truncated"):
            raise RepositoryError("Repository tree was truncated")
        files = {}
        for row in tree["tree"]:
            if not row["path"].startswith("config/") or row["type"] == "tree":
                continue
            path = safe_path(row["path"])
            if row.get("mode") != "100644" or row.get("type") != "blob" or row.get("size", MAX_FILE + 1) > MAX_FILE:
                raise ValueError("Only bounded regular config files are allowed")
            if len(files) >= 512:
                raise ValueError("Too many configuration files")
            blob = self.request("GET", "git/blobs/" + row["sha"])
            if blob.get("encoding") != "base64":
                raise RepositoryError("Unexpected repository blob encoding")
            raw = base64.b64decode(blob["content"].replace("\n", ""), validate=True)
            if len(raw) > MAX_FILE or hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest() != row["sha"]:
                raise ValueError("Git configuration blob hash mismatch")
            files[path] = raw.decode("utf-8")
            if sum(len(t.encode()) for t in files.values()) > MAX_TREE:
                raise ValueError("Configuration tree is too large")
        if not files:
            raise RepositoryError("Repository has no config artifacts")
        return restore_snapshot({"repository": self.repository, "branch": "main", "commit": commit,
                                 "files": _records(files)}, self.cache_dir)

    def validate(self, base_commit, changes):
        base = self.snapshot(base_commit)
        files = _texts(base["files"])
        if not isinstance(changes, list) or len(changes) > 512:
            raise ValueError("Expected a bounded list of file changes")
        seen, diff = set(), []
        for change in changes:
            name, text = safe_path(change["path"]), change["text"]
            if name in seen or (text is not None and (not isinstance(text, str) or len(text.encode()) > MAX_FILE)):
                raise ValueError("Duplicate or oversized file change")
            seen.add(name)
            old = files.get(name, "")
            if text is None:
                files.pop(name, None)
            else:
                files[name] = text
            diff.extend(difflib.unified_diff(old.splitlines(keepends=True), (text or "").splitlines(keepends=True), fromfile=name, tofile=name))
        problems = validate_files(files)
        previous = validate_files(_texts(base["files"]))
        # Historical incomplete plans stay visible but cannot be newly introduced
        # or edited into another invalid revision. Launch validation remains strict.
        warnings = [p for p in problems if p in previous and p.split(":", 1)[0] not in seen]
        errors = [p for p in problems if p not in warnings]
        return {"valid": not errors, "errors": errors, "warnings": warnings,
                "diff": "".join(diff), "files": files}

    def save(self, base_commit, changes, message, operator):
        if not self.token:
            raise RepositoryError("A server repository credential is required to save")
        if not isinstance(message, str) or not message.strip() or len(message) > 500:
            raise ValueError("Give this commit a message of at most 500 characters")
        if not isinstance(operator, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9 ._-]{0,79}", operator):
            raise ValueError("Name the operator saving this configuration")
        checked = self.validate(base_commit, changes)
        if not checked["valid"]:
            raise ValueError("; ".join(checked["errors"]))
        if self.head() != base_commit:
            raise Conflict("Main changed since this edit; refresh and review the differences")
        base = self.snapshot(base_commit)
        old = _texts(base["files"])
        if old == checked["files"]:
            return base
        tree_sha = self.request("GET", "git/commits/" + base_commit)["tree"]["sha"]
        entries = []
        for path in sorted(set(old) | set(checked["files"])):
            if old.get(path) != checked["files"].get(path):
                entries.append({"path": path, "mode": "100644", "type": "blob",
                                **({"content": checked["files"][path]} if path in checked["files"] else {"sha": None})})
        tree = self.request("POST", "git/trees", {"base_tree": tree_sha, "tree": entries})
        commit = self.request("POST", "git/commits", {"message": message.strip() + "\n\nDeclared operator: " + operator,
                                                    "tree": tree["sha"], "parents": [base_commit]})["sha"]
        if not SHA.fullmatch(commit):
            raise RepositoryError("Repository returned an invalid commit")
        try:
            self.request("PATCH", "git/refs/heads/main", {"sha": commit, "force": False})
        except Conflict:
            raise
        except RepositoryError:
            if self.head() != commit:
                raise RepositoryError("Save outcome is uncertain; check repository history before retrying") from None
        return self.snapshot(commit)
