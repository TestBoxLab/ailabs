"""A daily, deterministic index of the Monarch checkout for Genesis, and the read-only
code tools it answers with.

The job (`DAILY`, 04:00 São Paulo) fetches, resolves the ref under test to a commit,
records what moved since the last indexed commit, runs Graphify when its CLI is on
PATH, rewrites `MONARCH.md` from data (never from a model) and files the change record
in the Genesis library. Nothing here spends money or needs the network beyond `git fetch`.
Everything a tool returns is internal-only: code facts never reach a public report.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from wb_results.evidence import write_json
from wb_studio.library import now_sao_paulo

REPO = Path(__file__).resolve().parents[3]  # the AILabs checkout; same as wb_studio.app.REPO
BACKEND_SRC = "monarch-enterprise/apps/backend/src"
ROUTE = re.compile(r"@(Get|Post|Put|Patch|Delete)\(")
BINARY = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".woff", ".woff2", ".ttf", ".eot", ".otf",
          ".pdf", ".zip", ".gz", ".tar", ".jar", ".exe", ".dll", ".so", ".dylib", ".bin", ".wasm", ".map",
          ".lock", ".mp4", ".mp3", ".snap"}
MAX_FILE = 1_000_000
MONARCH_MD_LIMIT = 2500
INTERNAL = {"audience": "internal"}
TARGETS = ("monarch", "lab")  # the product under test, and the lab's own checkout (feature 023)


# -- settings and git -------------------------------------------------------------

def target(value) -> str:
    """The repository a call means: Monarch, the product under test, or the lab's own checkout."""
    name = str(value or "monarch").strip().lower()
    if name not in TARGETS:
        raise ValueError("repo is " + " or ".join(repr(t) for t in TARGETS))
    return name


def settings(studio, repo: str = "monarch") -> dict:
    which = target(repo)
    if which == "lab":
        # The lab's own checkout at whatever is checked out now; there is no declared build to pin to.
        return {"repo": REPO, "ref": "HEAD", "out": Path(studio.directory) / "genesis" / "code-index-lab",
                "build": None, "target": "lab"}
    from wb_studio.enterprise import environment
    env = environment(studio)
    path = Path(env.get("MONARCH_REPO") or REPO.parent / "monarch")
    ref = (env.get("MONARCH_BUILD_COMMIT") or "").strip()
    if not ref:
        declared = re.fullmatch(r"monarch@[0-9a-fA-F]+\+(.+)", (env.get("MONARCH_BUILD") or "").strip())
        ref = declared[1] if declared else "main"
    return {"repo": path, "ref": ref, "out": Path(studio.directory) / "genesis" / "code-index",
            "build": (env.get("MONARCH_BUILD") or "").strip() or None, "target": "monarch"}


def git(repo, *args, timeout=120) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], text=True, encoding="utf-8", errors="replace",
                          capture_output=True, timeout=timeout)
    if done.returncode:
        raise RuntimeError((done.stderr or done.stdout).strip() or f"git {args[0]} failed")
    return done.stdout


def _resolve(repo, ref) -> tuple[str, str]:
    """The commit a ref names: the remote branch after a fetch, else the local name, else HEAD."""
    for candidate in (f"origin/{ref}", ref, "HEAD"):
        try:
            return git(repo, "rev-parse", "--verify", "--quiet", candidate + "^{commit}").strip(), candidate
        except RuntimeError:
            continue
    raise RuntimeError(f"Cannot resolve {ref!r} in {repo}")


def tracked(repo, commit=None) -> list[str]:
    out = git(repo, "ls-tree", "-r", "--name-only", commit) if commit else git(repo, "ls-files")
    return [line for line in out.splitlines() if line]


def _area(path: str) -> str:
    return path.split("/", 1)[0] if "/" in path else "(root)"


# -- the change record ------------------------------------------------------------

def _count(items, key):
    counts: dict[str, int] = {}
    for item in items:
        counts[key(item)] = counts.get(key(item), 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def changes(repo, since: str, until: str) -> dict:
    """What moved between two commits, in the shape `changes.json` keeps."""
    files: dict[str, list[str]] = {"added": [], "modified": [], "deleted": []}
    for line in git(repo, "diff", "--name-status", "-M", f"{since}..{until}").splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0][0], parts[-1]
        files[{"A": "added", "D": "deleted"}.get(status, "modified")].append(path)
    touched = files["added"] + files["modified"] + files["deleted"]
    backend = [p[len(BACKEND_SRC) + 1:] for p in touched if p.startswith(BACKEND_SRC + "/")]
    versions = []
    for path in files["modified"]:
        if Path(path).name == "package.json":
            try:
                before = json.loads(git(repo, "show", f"{since}:{path}")).get("version")
                after = json.loads(git(repo, "show", f"{until}:{path}")).get("version")
            except (RuntimeError, ValueError, AttributeError):
                continue
            if before != after:
                versions.append({"package": path, "from": before, "to": after})
    routes: dict[str, list[dict]] = {"added": [], "removed": []}
    current = None
    for line in git(repo, "diff", "-U0", f"{since}..{until}", "--", "*.ts", "*.tsx", "*.js").splitlines():
        if line.startswith("+++ "):
            current = line[4:].removeprefix("b/")
        elif line.startswith(("+", "-")) and not line.startswith(("+++", "---")) and ROUTE.search(line):
            routes["added" if line[0] == "+" else "removed"].append({"path": current, "text": line[1:].strip()})
    return {"from": since, "to": until, "total": len(touched), "files": files,
            "by_area": _count(touched, _area),
            "backend": _count(backend, lambda p: p.split("/", 1)[0]),
            "versions": versions,
            "migrations": [p for p in files["added"] if "migrations" in Path(p).parts],
            "routes": routes}


def paragraph(record: dict | None) -> str:
    if not record or not record.get("total"):
        return "No change record yet: this is the first index, or nothing moved since the last one."
    files = record["files"]
    areas = ", ".join(list(record["by_area"])[:3])
    text = (f"{record['total']} files changed between {record['from'][:10]} and {record['to'][:10]}: "
            f"{len(files['added'])} added, {len(files['modified'])} modified, {len(files['deleted'])} deleted; "
            f"most touched: {areas}.")
    if record["backend"]:
        text += " Backend areas: " + ", ".join(f"{k} ({v})" for k, v in list(record["backend"].items())[:4]) + "."
    if record["versions"]:
        text += " Version bumps: " + ", ".join(f"{v['package']} {v['from']} to {v['to']}" for v in record["versions"][:3]) + "."
    if record["migrations"]:
        text += f" {len(record['migrations'])} migration(s) added."
    routes = record["routes"]
    if routes["added"] or routes["removed"]:
        text += f" Routes: {len(routes['added'])} added, {len(routes['removed'])} removed."
    return text


# -- Graphify ---------------------------------------------------------------------

def _graphify(repo, out: Path, commit: str, previous: dict) -> dict:
    report = out / "GRAPH_REPORT.md"
    have = report.exists()
    status = {"available": False, "report": str(report) if have else None,
              "built_from": previous.get("built_from") if have else None}
    if not shutil.which("graphify"):
        return status
    status["available"] = True
    try:
        subprocess.run(["graphify", "update", str(repo), "--code-only"], text=True, encoding="utf-8",
                       errors="replace", capture_output=True, timeout=900, check=True)
        source = repo / "graphify-out"
        for name in ("GRAPH_REPORT.md", "graph.json"):
            if (source / name).exists():
                shutil.copyfile(source / name, out / name)
        if report.exists():
            status.update(report=str(report), built_from=commit)
    except (subprocess.SubprocessError, OSError) as exc:
        status["error"] = f"Graphify did not finish: {type(exc).__name__}"
    return status


def god_nodes(report: Path) -> list[str]:
    """The god-node lines of a Graphify report, as plain text; empty when there is no such section."""
    try:
        text = report.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    section = re.search(r"^#+[^\n]*god nodes?[^\n]*\n(.*?)(?=^#+ |\Z)", text, re.I | re.M | re.S)
    if not section:
        return []
    lines = [re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", l).replace("**", "").replace("`", "").strip()
             for l in section[1].splitlines()]
    return [l for l in lines if l and not l.startswith("|")][:10]


def _graph(out: Path):
    """Nodes and edges of the copied graph.json, tolerant of the node-link shapes Graphify writes."""
    path = out / "graph.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    nodes = data.get("nodes") or []
    edges = data.get("edges") or data.get("links") or []
    return nodes, edges


def _node_view(node, edges):
    identity = node.get("id")
    degree = sum(1 for e in edges if identity in (e.get("source"), e.get("target")))
    return {"id": identity, "name": node.get("label") or node.get("name") or identity,
            "path": node.get("file_path") or node.get("path") or node.get("source_file"),
            "community": node.get("community"), "degree": degree}


# -- the daily job ----------------------------------------------------------------

def _monarch_md(cfg, index, record, nodes) -> str:
    counts = index["files"]
    lines = ["# Monarch (code index)", "",
             f"Build: {cfg['build'] or cfg['ref']}. Commit: {index['commit']}.",
             f"Ref followed: {index['ref']}. Indexed: {index['built_at'][:19]} UTC. Tracked files: {index['tracked_files']}.",
             "", "## Files by language",
             ", ".join(f"{ext or '(none)'} {n}" for ext, n in list(counts.items())[:8]) or "none",
             "", "## Layout",
             ", ".join(f"{d} {n}" for d, n in list(index["layout"].items())[:10]) or "none",
             "", "## Last change", paragraph(record)]
    if nodes:
        lines += ["", "## Graphify god nodes", "; ".join(nodes)]
    elif index["graphify"]["available"]:
        lines += ["", "Graphify ran but its report has no god nodes."]
    else:
        lines += ["", "Graphify is not installed here; only the file index and git history are available."]
    text = "\n".join(lines) + "\n"
    return text if len(text) <= MONARCH_MD_LIMIT else text[:MONARCH_MD_LIMIT - 4].rstrip() + "...\n"


def _safe(studio, repo: str) -> dict:
    try:
        return _refresh(studio, repo)
    except Exception as exc:  # the scheduler would catch this too; the summary is friendlier
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}


def refresh(studio) -> dict:
    """The daily job: Monarch's index, then the lab's own. Never raises. The top-level keys stay
    Monarch's, so a caller that reads `status` reads the product under test; `lab` carries the other."""
    summary = _safe(studio, "monarch")
    summary["lab"] = _safe(studio, "lab")
    return summary


def _refresh(studio, which: str = "monarch") -> dict:
    cfg = settings(studio, which)
    repo, out, lab = cfg["repo"], cfg["out"], cfg["target"] == "lab"
    if not (repo / ".git").exists():
        return {"status": "skipped", "reason": f"No {'lab' if lab else 'Monarch'} checkout at {repo}."
                                               + ("" if lab else " Set MONARCH_REPO or clone it there.")}
    out.mkdir(parents=True, exist_ok=True)
    index_path, changes_path = out / "index.json", out / "changes.json"
    previous = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    try:
        git(repo, "fetch", "--quiet")
        fetch = "ok"
    except (RuntimeError, subprocess.SubprocessError) as exc:
        fetch = f"failed: {str(exc).splitlines()[0][:200] if str(exc) else type(exc).__name__}"
    commit, resolved = _resolve(repo, cfg["ref"])
    files = tracked(repo, commit)
    index = {"commit": commit, "ref": cfg["ref"], "resolved_from": resolved, "build": cfg["build"],
             "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "previous_commit": previous.get("commit"), "fetch": fetch, "repo": str(repo),
             "worktree_commit": git(repo, "rev-parse", "HEAD").strip(),
             "files": _count(files, lambda p: Path(p).suffix.lower()), "tracked_files": len(files),
             "layout": _count(files, _area)}
    changed = bool(previous.get("commit")) and previous["commit"] != commit
    if changed:
        write_json(changes_path, changes(repo, previous["commit"], commit))
    record = json.loads(changes_path.read_text(encoding="utf-8")) if changes_path.exists() else None
    index["graphify"] = _graphify(repo, out, commit, previous.get("graphify") or {})
    write_json(index_path, index)
    nodes = god_nodes(out / "GRAPH_REPORT.md") if index["graphify"]["report"] else []
    if not lab:  # MONARCH.md describes the product under test; the lab's own code has no such summary
        (out / "MONARCH.md").write_text(_monarch_md(cfg, index, record, nodes), encoding="utf-8")
    summary = {"status": "completed", "commit": commit, "previous_commit": index["previous_commit"], "fetch": fetch,
               "tracked_files": len(files), "changed": changed, "graphify": index["graphify"]["available"]}
    if changed and record and record.get("total") and not lab:
        today = now_sao_paulo().date().isoformat()
        entry = studio.genesis.library.add({
            "title": f"Monarch changes {today}: {record['total']} files in {', '.join(list(record['by_area'])[:3])}",
            "url": f"{repo}@{commit}", "source_type": "repo", "topic": "Code understanding",
            "abstract": paragraph(record), "discovered_at": today})
        summary["library_record"] = entry["id"]
    return summary


DAILY = ("code-index", 4, refresh)


# -- read-only tools for Genesis --------------------------------------------------

def _readable(repo, path: str) -> bool:
    return Path(path).suffix.lower() not in BINARY and (repo / path).is_file() and (repo / path).stat().st_size <= MAX_FILE


def _lines(repo, path: str):
    try:
        return (repo / path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def code_status(studio, payload=None) -> dict:
    cfg = settings(studio, (payload or {}).get("repo"))
    index_path, md = cfg["out"] / "index.json", cfg["out"] / "MONARCH.md"
    if not index_path.exists():
        return {"indexed": False, "repo": str(cfg["repo"]), "ref": cfg["ref"], "target": cfg["target"],
                "message": f"The {cfg['target']} code index has not been built yet. Run wb genesis index or wait for the daily job.", **INTERNAL}
    return {"indexed": True, "target": cfg["target"], **json.loads(index_path.read_text(encoding="utf-8")),
            "monarch_md": md.read_text(encoding="utf-8") if md.exists() else "", **INTERNAL}


def code_search(studio, payload) -> dict:
    query = str(payload.get("query") or "").strip()
    if len(query) < 2:
        raise ValueError("Give a search of at least 2 characters")
    limit = max(1, min(100, int(payload.get("limit") or 30)))
    cfg = settings(studio, payload.get("repo"))
    repo, needle = cfg["repo"], query.lower()
    graph = _graph(cfg["out"])
    graph_hits = []
    if graph:
        nodes, edges = graph
        graph_hits = [_node_view(n, edges) for n in nodes
                      if needle in str(n.get("label") or n.get("name") or n.get("id") or "").lower()
                      or needle in str(n.get("file_path") or n.get("path") or "").lower()][:limit]
    hits = []
    if (repo / ".git").exists():
        for path in tracked(repo):  # ponytail: full scan each call; cache the file list if it ever feels slow
            if not _readable(repo, path):
                continue
            for number, text in enumerate(_lines(repo, path), 1):
                if needle in text.lower():
                    hits.append({"path": path, "line": number, "text": text.strip()[:300]})
                    if len(hits) >= limit:
                        break
            if len(hits) >= limit:
                break
    return {"query": query, "target": cfg["target"], "graph": graph_hits, "hits": hits, "limit": limit, **INTERNAL}


def code_explain(studio, payload) -> dict:
    symbol = str(payload.get("symbol") or "").strip()
    if not re.fullmatch(r"[A-Za-z_$][\w$]{0,199}", symbol):
        raise ValueError("Give one symbol name, such as a class or function")
    cfg = settings(studio, payload.get("repo"))
    repo = cfg["repo"]
    graph = _graph(cfg["out"])
    matches = []
    if graph:
        nodes, edges = graph
        for node in nodes:
            name = str(node.get("label") or node.get("name") or node.get("id") or "")
            if name == symbol or name.endswith("." + symbol) or name.endswith("::" + symbol):
                view = _node_view(node, edges)
                view["edges"] = [{"source": e.get("source"), "target": e.get("target"), "relation": e.get("relation") or e.get("type")}
                                 for e in edges if node.get("id") in (e.get("source"), e.get("target"))][:50]
                matches.append(view)
    definitions = []
    if not matches and (repo / ".git").exists():
        pattern = re.compile(r"\b(?:function|class|const|let|var|interface|type|enum|def|export)\b[^\n]{0,80}?\b" + re.escape(symbol) + r"\b")
        for path in tracked(repo):
            if not _readable(repo, path):
                continue
            for number, text in enumerate(_lines(repo, path), 1):
                if pattern.search(text):
                    definitions.append({"path": path, "line": number, "text": text.strip()[:300]})
                    if len(definitions) >= 30:
                        break
            if len(definitions) >= 30:
                break
    return {"symbol": symbol, "target": cfg["target"], "graph": matches, "definitions": definitions, **INTERNAL}


def code_read(studio, payload) -> dict:
    cfg = settings(studio, payload.get("repo"))
    inside = "Give a path inside the " + cfg["target"] + " checkout, relative to its root"
    raw = str(payload.get("path") or "").strip().replace("\\", "/")
    parts = Path(raw).parts
    if not raw or Path(raw).is_absolute() or raw.startswith("/") or ".." in parts or (parts and parts[0].endswith(":")):
        raise ValueError(inside)
    repo = cfg["repo"].resolve()
    full = (repo / raw).resolve()
    if not full.is_relative_to(repo) or not full.is_file():
        raise ValueError(inside)
    path = full.relative_to(repo).as_posix()
    if path not in set(tracked(repo)):
        raise ValueError("That file is not tracked in the " + cfg["target"] + " checkout")
    if not _readable(repo, path):
        raise ValueError("That file is binary or over 1 MB")
    lines = _lines(repo, path)
    start = max(1, int(payload.get("start") or 1))
    end = min(int(payload.get("end") or start + 199), start + 199, len(lines))
    return {"path": path, "target": cfg["target"], "start": start, "end": end, "total_lines": len(lines),
            "lines": [{"line": n, "text": lines[n - 1]} for n in range(start, end + 1)], **INTERNAL}


def code_changes(studio, payload) -> dict:
    cfg = settings(studio, payload.get("repo"))
    since = str(payload.get("since") or "").strip()
    if not since:
        path = cfg["out"] / "changes.json"
        record = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        return {"record": record, "target": cfg["target"], "summary": paragraph(record), **INTERNAL}
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", since):
        raise ValueError("since is a commit (7 to 40 hex characters)")
    repo = cfg["repo"]
    try:
        base = git(repo, "rev-parse", "--verify", "--quiet", since + "^{commit}").strip()
    except RuntimeError:
        raise ValueError("That commit is not in the " + cfg["target"] + " checkout") from None
    record = changes(repo, base, git(repo, "rev-parse", "HEAD").strip())
    return {"record": record, "target": cfg["target"], "summary": paragraph(record), **INTERNAL}


TOOLS = {"code_status": code_status, "code_search": code_search, "code_explain": code_explain,
         "code_read": code_read, "code_changes": code_changes}
