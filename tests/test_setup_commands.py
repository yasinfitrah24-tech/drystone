"""The judges' Setup tab stays in step with the code: the same `python tools/...` commands as the README, every option
known to the script's argparse, the key lists the same as the ones the tools handle, and copy buttons that copy
commands that run as they are. If a test fails, fix the page or the README; do not loosen the test.

    python -m pytest tests/test_setup_commands.py -q
"""
import html
import os
import re
import shlex
import subprocess
import sys

import pytest

import agent_hud
import calibrate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


PAGE = _read("web/index.html")
SETUP = PAGE[PAGE.index('id="view-setup"'):PAGE.index("<footer")]
README = _read("README.md")


def _plain(fragment):
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def copy_commands(fragment):
    """Every command that has a copy button."""
    return [_plain(c) for c in re.findall(r'<div class="code"><pre><code>(.*?)</code></pre><button type="button" class="copy"',
                                          fragment, re.S)]


def readme_commands():
    """Every line of the README's fenced code blocks."""
    lines = []
    for block in re.findall(r"^```[^\n]*\n(.*?)^```", README, re.S | re.M):
        lines += [l.strip() for l in block.splitlines() if l.strip()]
    return lines


def tool_commands(cmds):
    return sorted({c for c in cmds if c.startswith("python tools/")})


def test_setup_and_readme_run_the_same_tools_commands():
    page, readme = tool_commands(copy_commands(SETUP)), tool_commands(readme_commands())
    assert page, "no python tools/ command found on the Setup tab"
    assert set(page) - set(readme) == set(), "on the Setup tab but not in the README"
    assert set(readme) - set(page) == set(), "in the README but not on the Setup tab"


@pytest.fixture(scope="module")
def help_texts():
    texts = {}
    for cmd in tool_commands(copy_commands(SETUP)):
        script = shlex.split(cmd, posix=True)[1]
        if script not in texts:
            path = os.path.join(ROOT, script)
            assert os.path.isfile(path), f"{script} does not exist"
            out = subprocess.run([sys.executable, path, "--help"], cwd=ROOT, capture_output=True, text=True, timeout=120)
            assert out.returncode == 0, f"{script} --help failed: {out.stderr[-300:]}"
            texts[script] = out.stdout
    return texts


def test_every_option_is_known_to_the_script(help_texts):
    for cmd in tool_commands(copy_commands(SETUP)):
        parts = shlex.split(cmd, posix=True)
        known = set(re.findall(r"(--[a-z][a-z0-9-]*)", help_texts[parts[1]]))
        for opt in (p.split("=")[0] for p in parts[2:] if p.startswith("--")):
            assert opt in known, f"{cmd}: {opt} is not an option of {parts[1]}"


def _keys_on_page(name):
    m = re.search(r'<p class="fine keys" data-keys="%s">(.*?)</p>' % name, SETUP, re.S)
    assert m, f"no key list for {name} on the Setup tab"
    pairs = re.findall(r"<kbd>(.*?)</kbd>\s*([^<]*?)\s*(?:&middot;|$)", m.group(1).strip())
    return [(html.unescape(k), html.unescape(v).strip()) for k, v in pairs]


def test_calibration_keys_are_the_ones_the_tool_handles():
    assert _keys_on_page("calibrate") == list(calibrate.KEYS["guided"])
    keys = ", ".join(f"{k} {v}" for k, v in calibrate.KEYS["guided"])
    assert "Keys in the calibration window: " + keys.replace(", ", " · ") in README


def test_agent_keys_are_the_ones_the_agent_handles():
    assert _keys_on_page("agent") == list(agent_hud.AGENT_KEYS)
    assert "Keys in the agent window: " + " · ".join(f"{k} {v}" for k, v in agent_hud.AGENT_KEYS) in README
    # and agent.py reacts to each of them in its window loop
    src = _read("tools/agent.py")
    for k, _ in agent_hud.AGENT_KEYS:
        for letter in ("a", "d") if k == "A / D" else (" ",) if k == "SPACE" else (k.lower(),):
            assert f'ord("{letter}")' in src, f"agent.py does not handle {k}"


def test_calibration_loop_handles_exactly_its_key_lists():
    src = _read("tools/calibrate.py")
    assert 'allowed = {k for k, _ in KEYS[mode]}' in src            # keys outside the list are ignored
    for k in {k for keys in calibrate.KEYS.values() for k, _ in keys}:
        assert f'press == "{k}"' in src, f"calibrate.py does not handle {k}"


def test_copy_commands_have_no_placeholders():
    cmds = copy_commands(PAGE)
    assert len(cmds) > 20
    assert not [c for c in cmds if "<" in c or ">" in c]
