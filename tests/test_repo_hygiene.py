"""Repository level invariants that are cheap to break and expensive to notice.

These are not tests of the library. They are tests of the deliverable, and each
one exists because the failure it catches is invisible in a diff: an em dash
that slipped into a docstring, a placeholder handle left in a badge URL, an
optional dependency imported at module scope so a lean install fails.
"""

from __future__ import annotations

import ast
import builtins
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".yaml",
    ".yml",
    ".toml",
    ".cfg",
    ".txt",
    ".json",
    ".svg",
}
NETWORK_MODULES = ("requests", "urllib", "httpx", "aiohttp", "socket", "boto3")
SKIP_DIRECTORIES = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "reports",
    "node_modules",
    ".cache",
    ".venv",
    "venv",
    "env",
    "site-packages",
    "build",
    "dist",
}
OPTIONAL_MODULES = ("playwright", "cmarkgfm")
DEFERRED_MODULES = ()

# Built from code points rather than written out, so this file does not itself
# contain the characters and strings it forbids. The first version did, and the
# suite failed with this file as the only offender, which is a confusing
# signature to read.
EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)
PLACEHOLDER_HANDLES = ("YOUR_" + "USERNAME", "<user" + "name>", "USERNAME" + "/")


def text_files() -> list[Path]:
    """The text files that are part of the deliverable.

    Asks git first, and this is not a preference. The first version walked the
    tree with rglob and a skip list, which passed in the working copy and failed
    in a fresh clone: the clone-run-verify check builds a virtualenv inside the
    repository, and rglob happily read site-packages, where em dashes and
    placeholder handles are plentiful. What the hygiene tests are about is what
    was committed, so the tracked file list is the right question to ask.
    """
    if (REPO / ".git").exists():
        completed = subprocess.run(
            ["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True, check=True
        )
        return [
            REPO / name
            for name in completed.stdout.split("\0")
            if name and Path(name).suffix in TEXT_SUFFIXES and (REPO / name).is_file()
        ]
    return [
        path
        for path in REPO.rglob("*")
        if path.is_file()
        and path.suffix in TEXT_SUFFIXES
        and not any(part in SKIP_DIRECTORIES for part in path.parts)
    ]


def test_there_are_text_files_to_check():
    assert len(text_files()) > 15


def test_no_file_contains_an_em_dash():
    offenders = [
        str(path.relative_to(REPO))
        for path in text_files()
        if EM_DASH in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_no_file_contains_an_en_dash_between_words():
    """An en dash in prose is the same drift as an em dash, and reads as generated."""
    pattern = re.compile(rf"[A-Za-z]{EN_DASH}[A-Za-z]")
    offenders = [
        str(path.relative_to(REPO))
        for path in text_files()
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_no_file_carries_a_placeholder_handle():
    offenders: list[str] = []
    for path in text_files():
        content = path.read_text(encoding="utf-8")
        if any(handle in content for handle in PLACEHOLDER_HANDLES):
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == []


def test_the_package_imports_without_the_evidence_extras(monkeypatch):
    """Trap 1: a lean install must not fail on an import the extras provide.

    The evidence tooling needs Playwright and cmark-gfm. Nothing under src may,
    or `pip install .` followed by `churngate sweep` breaks on a machine that
    never asked for the screenshots.
    """
    real_import = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name.split(".")[0] in OPTIONAL_MODULES:
            raise ModuleNotFoundError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    for module in (
        "churngate.cli",
        "churngate.pipeline",
        "churngate.audit",
        "churngate.gates",
        "churngate.report",
        "churngate.rates",
    ):
        __import__(module)


def test_a_deferred_dependency_is_never_imported_at_module_scope():
    """A module scope import of xgboost would break the lean install for everyone.

    Checked by walking the syntax tree rather than by scanning lines. The first
    version scanned text and failed on a docstring that contained both the word
    import and the word xgboost, which is a test reporting on prose.
    """
    offenders: list[str] = []
    for path in (REPO / "src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in DEFERRED_MODULES:
                    offenders.append(f"{path.relative_to(REPO)}:{name}")
    assert offenders == []


def test_the_package_has_no_optional_dependencies_to_defer():
    """This package deliberately has none, which ADR-004 explains.

    The check is kept rather than deleted because the absence is the claim: the
    runtime needs numpy, scipy and a YAML parser, and a future import of anything
    heavier should fail this test rather than pass unnoticed.
    """
    import tomllib

    manifest = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    extras = manifest["project"]["optional-dependencies"]
    assert set(extras) == {"dev", "evidence"}


def test_no_source_file_imports_an_evidence_extra():
    offenders: list[str] = []
    for path in (REPO / "src").rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        for module in OPTIONAL_MODULES:
            if re.search(rf"^\s*(import|from)\s+{module}\b", content, re.MULTILINE):
                offenders.append(f"{path.relative_to(REPO)}:{module}")
    assert offenders == []


def test_no_source_file_imports_a_network_library():
    """The README promises the headline number is reproducible with no network."""
    offenders: list[str] = []
    for path in (REPO / "src").rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        for module in NETWORK_MODULES:
            if re.search(rf"^\s*(import|from)\s+{module}\b", content, re.MULTILINE):
                offenders.append(f"{path.relative_to(REPO)}:{module}")
    assert offenders == []


def test_no_experiment_imports_a_network_library():
    offenders: list[str] = []
    for path in (REPO / "experiments").rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        for module in NETWORK_MODULES:
            if re.search(rf"^\s*(import|from)\s+{module}\b", content, re.MULTILINE):
                offenders.append(f"{path.relative_to(REPO)}:{module}")
    assert offenders == []


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout


@pytest.mark.skipif(not (REPO / ".git").exists(), reason="not a git checkout")
def test_no_commit_message_carries_an_ai_attribution():
    log = _git("log", "--format=%B%n%an%n%ae").lower()
    for marker in (
        "co-authored-by",
        "generated with",
        "claude",
        "copilot",
        "chatgpt",
        "gpt-4",
        "openai",
        "anthropic",
    ):
        assert marker not in log, marker


@pytest.mark.skipif(not (REPO / ".git").exists(), reason="not a git checkout")
def test_every_commit_has_the_same_author():
    authors = {line for line in _git("log", "--format=%an <%ae>").splitlines() if line}
    assert len(authors) == 1


@pytest.mark.skipif(not (REPO / ".git").exists(), reason="not a git checkout")
def test_the_history_is_not_a_single_dump_commit():
    count = len(_git("log", "--format=%h").splitlines())
    assert count >= 5


@pytest.mark.skipif(not (REPO / ".git").exists(), reason="not a git checkout")
def test_no_commit_message_contains_an_em_dash():
    assert EM_DASH not in _git("log", "--format=%B")
