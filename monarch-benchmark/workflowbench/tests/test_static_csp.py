"""The Studio ships under `style-src 'self'; script-src 'self'`: no inline styles,
no external scripts, styles or fonts, and no hex colours outside the token sheet
and the vendored scales. These checks fail before a browser ever would."""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "wb_studio" / "static"
TEXT_SUFFIXES = {".html", ".js", ".css", ".svg"}
HEX = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])")


def static_files():
    return sorted(p for p in STATIC.rglob("*") if p.suffix in TEXT_SUFFIXES and p.is_file())


def test_static_files_exist():
    names = {p.name for p in static_files()}
    assert {"index.html", "tokens.css", "ui.css", "app.js", "sprite.svg", "radix-colors.css"} <= names


def test_no_inline_style_attributes_or_style_elements():
    offenders = []
    for path in static_files():
        text = path.read_text(encoding="utf-8")
        if re.search(r"\sstyle\s*=\s*[\"']", text) or re.search(r"<style[\s>]", text, re.I):
            offenders.append(path.relative_to(STATIC).as_posix())
    assert offenders == []


def test_no_external_resources():
    """Hyperlinks to the outside are fine; loading scripts, styles, fonts or
    images from another origin is not."""
    patterns = [
        re.compile(r"<(?:script|link|img|iframe)[^>]*(?:src|href)\s*=\s*[\"']https?://", re.I),
        re.compile(r"url\(\s*[\"']?https?://", re.I),
        re.compile(r"@import\b", re.I),
        re.compile(r"(?:fetch|EventSource|XMLHttpRequest)\(\s*[\"'`]https?://"),
        re.compile(r"\bimport\(\s*[\"'`]https?://"),
    ]
    offenders = [(p.relative_to(STATIC).as_posix(), pat.pattern) for p in static_files()
                 for pat in patterns if pat.search(p.read_text(encoding="utf-8"))]
    assert offenders == []


def test_colours_live_only_in_tokens_and_vendor():
    offenders = {}
    for path in static_files():
        if path.name == "tokens.css" or "vendor" in path.parts:
            continue
        found = HEX.findall(path.read_text(encoding="utf-8"))
        if found:
            offenders[path.relative_to(STATIC).as_posix()] = sorted(set(found))[:8]
    assert offenders == {}


def test_no_important_rules():
    offenders = [p.name for p in static_files() if p.suffix == ".css" and "!important" in p.read_text(encoding="utf-8")]
    assert offenders == []


def test_layer_order_is_declared_once_first():
    tokens = (STATIC / "tokens.css").read_text(encoding="utf-8")
    assert tokens.lstrip().startswith("/*") or tokens.lstrip().startswith("@layer")
    assert "@layer tokens, base, components, views, utilities;" in tokens
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    links = re.findall(r'<link rel="stylesheet" href="([^"]+)"', index)
    assert links[:3] == ["/vendor/radix-colors/radix-colors.css", "/tokens.css", "/ui.css"]
    for name in ("style.css", "workspace.css", "graph.css", "analytics.css", "genesis.css", "studio-library.css"):
        assert (STATIC / name).read_text(encoding="utf-8").lstrip().startswith("@layer views{"), name


def test_fonts_are_served_locally():
    tokens = (STATIC / "tokens.css").read_text(encoding="utf-8")
    for url in re.findall(r"url\(([^)]+)\)", tokens):
        url = url.strip("\"'")
        assert url.startswith("/vendor/plex/"), url
        assert (STATIC / url.lstrip("/")).is_file(), url
