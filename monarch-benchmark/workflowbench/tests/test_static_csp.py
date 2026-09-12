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
        # A socket to another origin is an external resource even though it does not look
        # like one, and `connect-src` governs it. Every pattern above keys on the http(s)
        # scheme and misses it entirely (feature 024 voice research).
        re.compile(r"new\s+WebSocket\(\s*[\"'`]wss?://"),
        # RTCPeerConnection is worse: CSP does not govern WebRTC at all, so a browser
        # would not refuse it either. Only the explicitly selected GPT-Live transport may open one.
        re.compile(r"\bRTCPeerConnection\b"),
    ]
    offenders = [(p.relative_to(STATIC).as_posix(), pat.pattern) for p in static_files()
                 for pat in patterns if not (p.name == "voice-live.js" and pat.pattern == r"\bRTCPeerConnection\b")
                 and pat.search(p.read_text(encoding="utf-8"))]
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
        assert url.startswith(("/vendor/plex/", "/vendor/newsreader/")), url
        assert (STATIC / url.lstrip("/")).is_file(), url


def test_no_infinite_animation_beside_interactive_content():
    """WCAG 2.2.2 Level A: motion that starts automatically, runs over five seconds and
    sits beside other content needs a mechanism to pause, stop or hide it.

    The Studio has no such mechanism, so nothing here may loop indefinitely. A status
    that pulsed forever was shipping as a Level A failure, and a static mark plus the
    word beside it carries the same information. A finite animation — one that reacts to
    an event and stops — is fine and is not matched here.
    """
    offenders = []
    for path in static_files():
        if path.suffix != ".css" or "vendor" in path.parts:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if re.search(r"animation:[^;}]*\binfinite\b", line):
                offenders.append(f"{path.name}: {line.strip()[:80]}")
    assert offenders == []


def test_motion_is_opt_in_rather_than_switched_off_afterwards():
    """Declare motion inside `@media (prefers-reduced-motion: no-preference)`.

    A `reduce` override ships full motion to any browser that does not support the
    feature. It also cannot stop a transform written from JavaScript, which is how an
    amplitude-driven indicator would reach a reduced-motion user at full swing while the
    blanket rule at the end of ui.css appeared to cover it.

    ui.css is exempt: it holds that blanket rule itself.
    """
    offenders = []
    for path in static_files():
        if path.suffix != ".css" or "vendor" in path.parts or path.name == "ui.css":
            continue
        text = path.read_text(encoding="utf-8")
        opt_in = re.search(r"prefers-reduced-motion\s*:\s*no-preference", text)
        if "@keyframes" in text and not opt_in:
            offenders.append(path.name)
    assert offenders == []
