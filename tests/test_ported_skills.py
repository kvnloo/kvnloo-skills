"""Contract tests for the ported software-development skills."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CATEGORY = ROOT / "software-development"
PORTED = [
    "repository-architecture-audits",
    "secure-autonomous-experimentation",
    "fail-closed-code-review",
    "coding-session-continuity",
    "comparative-visual-build-audits",
    "multi-agent-release-readiness",
]

# Shapes that must never appear in a public skill.
PRIVATE_PATTERNS = [
    r"/home/",
    r"/mnt/",
    r"/workspace/",
    r"/Users/",
    r"@gmail\.com",
    r"\bsk-[A-Za-z0-9]{8,}",
    r"\bghp_[A-Za-z0-9]{8,}",
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"\b100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b",
]


def _skill(name: str) -> Path:
    return CATEGORY / name / "SKILL.md"


def _frontmatter(text: str) -> dict[str, str]:
    assert text.startswith("---\n")
    end = text.index("\n---\n", 4)
    out = {}
    for line in text[4:end].splitlines():
        m = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip().strip('"')
    return out


@pytest.mark.parametrize("name", PORTED)
def test_frontmatter(name):
    fm = _frontmatter(_skill(name).read_text(encoding="utf-8"))
    assert fm["name"] == name
    assert fm["description"].startswith("Use when ")
    assert len(fm["description"]) <= 60
    assert fm["description"].endswith(".")
    assert fm["license"] == "MIT"
    assert fm["platforms"].startswith("[")


@pytest.mark.parametrize("name", PORTED)
def test_size_and_sections(name):
    text = _skill(name).read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 150
    for section in ("## When to Use", "## Pitfalls", "## Verification", "## Credits"):
        assert section in text, f"{name} missing {section}"
    assert text.index("## When to Use") < text.index("## Pitfalls") < text.index("## Verification")


@pytest.mark.parametrize("name", PORTED)
def test_related_skills_resolve_in_repo(name):
    text = _skill(name).read_text(encoding="utf-8")
    m = re.search(r"related_skills:\s*\[(.*)\]", text)
    assert m
    present = {p.parent.name for p in ROOT.glob("*/*/SKILL.md")}
    for rel in filter(None, (s.strip() for s in m.group(1).split(","))):
        assert rel in present, f"{name} -> {rel} not in repo"


@pytest.mark.parametrize("name", PORTED)
def test_local_links_resolve(name):
    skill_dir = CATEGORY / name
    text = _skill(name).read_text(encoding="utf-8")
    for target in re.findall(r"\]\(((?:references|templates|scripts)/[^)]+)\)", text):
        assert (skill_dir / target).is_file(), f"{name}: broken link {target}"


def test_no_private_shapes_in_ported_files():
    hits = []
    for name in PORTED:
        for path in (CATEGORY / name).rglob("*"):
            if not path.is_file():
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for pat in PRIVATE_PATTERNS:
                    if re.search(pat, line):
                        hits.append(f"{path.relative_to(ROOT)}:{lineno}: {pat}")
    assert not hits, "\n".join(hits)


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def _review_manifest(repo: Path) -> str:
    """Same manifest the fail-closed-code-review skill tells reviewers to build."""
    script = (
        "{ git diff HEAD --name-only -z; git ls-files --others --exclude-standard -z; } | "
        "while IFS= read -r -d '' f; do "
        "if [ -e \"$f\" ] || [ -L \"$f\" ]; then printf '%s  %s\\n' \"$(git hash-object -- \"$f\")\" \"$f\"; "
        "else printf 'DELETED  %s\\n' \"$f\"; fi; done"
    )
    return subprocess.run(
        ["bash", "-c", script], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_review_manifest_catches_untracked_rewrite_that_status_misses(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "-c", "user.email=a@example.com", "-c", "user.name=a",
         "commit", "-q", "--allow-empty", "-m", "base")
    (repo / "tracked.txt").write_text("v1\n")
    _git(repo, "add", "tracked.txt")
    _git(repo, "-c", "user.email=a@example.com", "-c", "user.name=a",
         "commit", "-q", "-m", "add")
    (repo / "tracked.txt").write_text("v2\n")
    (repo / "new.py").write_text("print('one')\n")

    status_before = _git(repo, "status", "--short")
    stat_before = _git(repo, "diff", "HEAD", "--stat")
    manifest_before = _review_manifest(repo)
    assert "new.py" in manifest_before and "tracked.txt" in manifest_before

    # Another agent rewrites the untracked file mid-review.
    (repo / "new.py").write_text("print('two')\n")

    assert _git(repo, "status", "--short") == status_before
    assert _git(repo, "diff", "HEAD", "--stat") == stat_before
    assert _review_manifest(repo) != manifest_before


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_jury_contact_sheet_recipe_runs(tmp_path):
    clip = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x120:rate=24:duration=2",
         "-pix_fmt", "yuv420p", str(clip)],
        check=True,
    )
    for side, x in (("A", "0"), ("B", "iw/2")):
        out = tmp_path / f"{side}-sheet.png"
        vf = (f"fps=6,crop=iw/2:ih:{x}:0,"
              "drawtext=text='%{pts\\:hms}':x=8:y=8:fontcolor=white:box=1,tile=6x6")
        result = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(clip), "-vf", vf, "-frames:v", "1", str(out)],
            capture_output=True, text=True,
        )
        if result.returncode != 0 and "drawtext" in result.stderr:
            pytest.skip("ffmpeg built without drawtext")
        assert result.returncode == 0, result.stderr
        assert out.stat().st_size > 0
