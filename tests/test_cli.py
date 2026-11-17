import json

import pytest

from token_budget.cli import main
from token_budget.report import build, by_directory, render
from token_budget.scanner import FileStat, ScanResult


@pytest.fixture
def project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x" * 4000, encoding="utf-8")
    (tmp_path / "README.md").write_text("y" * 400, encoding="utf-8")
    (tmp_path / "pic.png").write_bytes(b"\x89PNG")
    return tmp_path


def run(capsys, *argv):
    code = main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_text_output_marks_estimates(project, capsys):
    code, out, _ = run(capsys, str(project), "--no-color")
    assert code == 0
    assert "~1,100" in out
    assert "src/a.py" in out and "By directory" in out
    assert "Skipped: 1" in out
    assert "\033[" not in out


def test_json_is_valid_and_complete(project, capsys):
    code, out, _ = run(capsys, str(project), "--json", "--limit", "2000")
    data = json.loads(out)
    assert code == 0
    assert data["total_tokens"] == 1100
    assert data["approximate"] is True
    assert data["fits"] is True and data["percent"] == 55.0
    assert data["skipped"]["total"] == 1


def test_does_not_fit_exit_code_1(project, capsys):
    code, out, _ = run(capsys, str(project), "--limit", "500", "--no-color")
    assert code == 1
    assert "does not fit" in out


def test_model_preset(project, capsys):
    code, out, _ = run(capsys, str(project), "--model", "claude", "--json")
    assert json.loads(out)["limit"] == 200_000


def test_limit_overrides_model(project, capsys):
    _, out, _ = run(capsys, str(project), "--model", "claude", "--limit", "5000", "--json")
    assert json.loads(out)["limit"] == 5000


def test_ext_and_exclude_flags(project, capsys):
    _, out, _ = run(capsys, str(project), "--ext", ".py", "--json")
    assert [f["path"] for f in json.loads(out)["top_files"]] == ["src/a.py"]
    _, out, _ = run(capsys, str(project), "--exclude", "src,*.png", "--json")
    assert [f["path"] for f in json.loads(out)["top_files"]] == ["README.md"]


def test_top_limits_list(project, capsys):
    _, out, _ = run(capsys, str(project), "--top", "1", "--json")
    assert len(json.loads(out)["top_files"]) == 1


def test_missing_path_exit_2(capsys):
    code, _, err = run(capsys, "/definitely/not/here")
    assert code == 2 and "no such path" in err


def test_bad_limit_exit_2(project, capsys):
    code, _, err = run(capsys, str(project), "--limit", "0")
    assert code == 2


def test_exact_without_tiktoken(project, capsys, monkeypatch):
    import token_budget.cli as cli

    def fail():
        raise RuntimeError("--exact needs tiktoken")

    monkeypatch.setattr(cli, "get_exact_counter", fail)
    code, _, err = run(capsys, str(project), "--exact")
    assert code == 2 and "tiktoken" in err


def test_exact_mode_output_has_no_tilde(project, capsys, monkeypatch):
    import token_budget.cli as cli

    monkeypatch.setattr(cli, "get_exact_counter", lambda: (lambda t: len(t.split()) or 1))
    _, out, _ = run(capsys, str(project), "--exact", "--no-color", "--json")
    data = json.loads(out)
    assert data["approximate"] is False
    code, out, _ = run(capsys, str(project), "--exact", "--no-color")
    assert "~" not in out


def test_empty_folder(tmp_path, capsys):
    code, out, _ = run(capsys, str(tmp_path), "--no-color")
    assert code == 0 and "0 files" in out


def test_color_enabled_on_tty(monkeypatch):
    import sys

    from token_budget import cli

    class A:
        no_color = False
        json = False

    monkeypatch.setattr(sys, "stdout", type("T", (), {"isatty": lambda self: True})())
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert cli._use_color(A()) is True


def test_color_disabled_by_env(monkeypatch):
    from token_budget import cli

    class A:
        no_color = False
        json = False

    monkeypatch.setenv("NO_COLOR", "1")
    assert cli._use_color(A()) is False


def test_render_color_codes():
    r = ScanResult(root=".", files=[FileStat("a.py", 100)])
    text = render(build(r, 50, 5, 1, False), color=True)
    assert "\033[31m" in text  # red: does not fit


def test_by_directory_depth():
    r = ScanResult(root=".", files=[
        FileStat("a/b/c.py", 10), FileStat("a/d.py", 5), FileStat("top.py", 1)])
    assert by_directory(r, 1)[0] == {"dir": "a/", "tokens": 15, "files": 2}
    assert {d["dir"] for d in by_directory(r, 2)} == {"a/b/", "a/", "./"}


def test_module_entry_point(project):
    import subprocess
    import sys

    p = subprocess.run([sys.executable, "-m", "token_budget", str(project), "--json"],
                       capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 0
    assert json.loads(p.stdout)["file_count"] == 2
