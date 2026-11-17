import os
import time

import pytest

from token_budget.scanner import is_binary, scan


def write(root, rel, content="x" * 40):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        p.write_bytes(content)
    else:
        p.write_text(content, encoding="utf-8")
    return p


def paths(result):
    return {f.path for f in result.files}


def test_basic_scan_sorted_and_totals(tmp_path):
    write(tmp_path, "small.txt", "x" * 8)
    write(tmp_path, "src/big.py", "x" * 400)
    r = scan(str(tmp_path))
    assert [f.path for f in r.files] == ["src/big.py", "small.txt"]
    assert r.total_tokens == 102


def test_gitignore_respected(tmp_path):
    write(tmp_path, ".gitignore", "*.log\nsecret/\n")
    write(tmp_path, "a.py")
    write(tmp_path, "a.log")
    write(tmp_path, "secret/k.txt")
    r = scan(str(tmp_path))
    assert paths(r) == {".gitignore", "a.py"}
    assert r.skipped_total == 2


def test_gitignore_can_be_disabled(tmp_path):
    write(tmp_path, ".gitignore", "*.log\n")
    write(tmp_path, "a.log")
    assert "a.log" in paths(scan(str(tmp_path), use_gitignore=False))


def test_nested_gitignore(tmp_path):
    write(tmp_path, "sub/.gitignore", "*.tmp\n")
    write(tmp_path, "sub/a.tmp")
    write(tmp_path, "sub/a.py")
    write(tmp_path, "b.tmp")
    assert paths(scan(str(tmp_path))) == {"sub/.gitignore", "sub/a.py", "b.tmp"}


def test_default_skip_dirs_and_counted(tmp_path):
    write(tmp_path, "node_modules/x/index.js")
    write(tmp_path, ".git/config")
    write(tmp_path, "keep.py")
    r = scan(str(tmp_path))
    assert paths(r) == {"keep.py"}
    assert r.skipped_total == 2


def test_binary_skipped_by_ext_and_content(tmp_path):
    write(tmp_path, "img.png", b"\x89PNG")
    write(tmp_path, "blob.dat", b"ab\x00cd")
    write(tmp_path, "ok.txt")
    r = scan(str(tmp_path))
    assert paths(r) == {"ok.txt"}
    assert r.skipped["binary"] == 2


def test_is_binary_unreadable_is_false(tmp_path):
    assert is_binary(str(tmp_path / "missing.txt")) is False


def test_ext_filter(tmp_path):
    write(tmp_path, "a.py")
    write(tmp_path, "b.md")
    write(tmp_path, "c.PY")
    assert paths(scan(str(tmp_path), exts=["py"])) == {"a.py", "c.PY"}
    assert paths(scan(str(tmp_path), exts=[".md"])) == {"b.md"}


def test_exclude_globs(tmp_path):
    write(tmp_path, "a.py")
    write(tmp_path, "tests/t.py")
    write(tmp_path, "gen/x.py")
    r = scan(str(tmp_path), excludes=["tests", "gen/*.py"])
    assert paths(r) == {"a.py"}


def test_non_utf8_file_is_counted_not_crashing(tmp_path):
    write(tmp_path, "latin.txt", "café".encode("latin-1") * 20)
    assert paths(scan(str(tmp_path))) == {"latin.txt"}


def test_single_file_path(tmp_path):
    f = write(tmp_path, "one.txt", "x" * 16)
    r = scan(str(f))
    assert r.total_tokens == 4
    assert paths(r) == {"one.txt"}


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_symlinks_not_followed(tmp_path):
    write(tmp_path, "real/a.txt")
    os.symlink(str(tmp_path), str(tmp_path / "real" / "loop"))
    os.symlink(str(tmp_path / "real" / "a.txt"), str(tmp_path / "link.txt"))
    r = scan(str(tmp_path))
    assert paths(r) == {"real/a.txt"}
    assert r.skipped["symlink"] == 2  # file link + directory link


@pytest.mark.skipif(os.name == "nt", reason="chmod semantics differ on Windows")
@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads anything")
def test_unreadable_file(tmp_path):
    f = write(tmp_path, "locked.txt")
    f.chmod(0)
    try:
        assert scan(str(tmp_path)).skipped.get("unreadable") == 1
    finally:
        f.chmod(0o644)


def test_unreadable_via_monkeypatch(tmp_path, monkeypatch):
    write(tmp_path, "a.txt")
    import token_budget.scanner as s

    def boom(*a, **k):
        raise OSError("nope")

    monkeypatch.setattr(s, "count_file", boom)
    assert scan(str(tmp_path)).skipped["unreadable"] == 1


def test_unreadable_directory(tmp_path, monkeypatch):
    write(tmp_path, "a.txt")
    import token_budget.scanner as s

    real = os.scandir

    def fake(path):
        raise OSError("denied")

    monkeypatch.setattr(s.os, "scandir", fake)
    assert scan(str(tmp_path)).skipped["unreadable"] == 1
    monkeypatch.setattr(s.os, "scandir", real)


def test_ten_thousand_files_is_fast(tmp_path):
    for d in range(100):
        sub = tmp_path / f"d{d}"
        sub.mkdir()
        for i in range(100):
            (sub / f"f{i}.txt").write_text("hello world " * 5, encoding="utf-8")
    start = time.time()
    r = scan(str(tmp_path))
    elapsed = time.time() - start
    assert len(r.files) == 10_000
    assert elapsed < 10
