import json
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _read(rel):
    return (_ROOT / rel).read_text(encoding="utf-8")


def test_readme_has_no_stale_seven_skills():
    readme = _read("README.md")
    assert "7 skills" not in readme
    assert "all 9 skills" in readme


def test_plugin_version_is_0_9_0():
    plugin = json.loads(_read(".claude-plugin/plugin.json"))
    assert plugin["version"] == "0.9.0"


def test_pyproject_version_matches_plugin():
    plugin = json.loads(_read(".claude-plugin/plugin.json"))
    pyproject = _read("pyproject.toml")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', pyproject)
    assert match, "pyproject.toml has no version field"
    assert match.group(1) == plugin["version"]


def test_changelog_has_current_and_historical_entries():
    changelog = _read("CHANGELOG.md")
    assert "## 0.9.0" in changelog
    assert "## 0.8.0" in changelog
    assert "## 0.7.0" in changelog
    assert "## 0.6.1" in changelog
    assert "## 0.6.0" in changelog
    assert "## 0.5.0" in changelog
    assert "## 0.3.4" in changelog
    assert "## 0.3.3" in changelog
    assert "## 0.3.2" in changelog
    assert "## 0.3.1" in changelog


def test_changelog_keeps_historical_seven_to_nine_lines():
    changelog = _read("CHANGELOG.md")
    assert "7 to 9 skills" in changelog
    assert "7 → 9" in changelog


def test_changelog_entry_has_no_anticheat_comment_shapes():
    changelog = _read("CHANGELOG.md")
    for line in changelog.splitlines():
        assert not re.search(
            r"#\s*(expected|hardcode|hack|cheat|to pass)", line, re.IGNORECASE
        ), line
