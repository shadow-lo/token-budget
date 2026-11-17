import pytest

from token_budget import tokens


def test_estimate_rounds_up():
    assert tokens.estimate(0) == 0
    assert tokens.estimate(1) == 1
    assert tokens.estimate(4) == 1
    assert tokens.estimate(5) == 2


def test_count_file_utf8(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("ü" * 40, encoding="utf-8")  # 40 chars, 80 bytes
    assert tokens.count_file(str(f)) == 10


def test_count_file_invalid_utf8_does_not_raise(tmp_path):
    f = tmp_path / "bad.txt"
    f.write_bytes(b"abc\xff\xfe" * 10)
    assert tokens.count_file(str(f)) > 0


def test_count_file_streams_across_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr(tokens, "CHUNK", 7)  # splits multibyte chars mid-way
    f = tmp_path / "a.txt"
    f.write_text("é" * 100, encoding="utf-8")
    assert tokens.count_file(str(f)) == 25


def test_count_file_with_custom_counter(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("one two three", encoding="utf-8")
    assert tokens.count_file(str(f), exact=lambda t: len(t.split())) == 3


def test_count_empty_file(tmp_path):
    f = tmp_path / "e.txt"
    f.write_bytes(b"")
    assert tokens.count_file(str(f)) == 0
    assert tokens.count_file(str(f), exact=lambda t: 99) == 0


def test_exact_counter_missing(monkeypatch):
    import builtins

    real = builtins.__import__

    def fake(name, *a, **k):
        if name == "tiktoken":
            raise ImportError
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)
    with pytest.raises(RuntimeError, match="tiktoken"):
        tokens.get_exact_counter()


def test_exact_counter_with_fake_tiktoken(monkeypatch):
    import sys
    import types

    class Enc:
        def encode(self, text, disallowed_special=()):
            return text.split()

    fake = types.SimpleNamespace(get_encoding=lambda name: Enc())
    monkeypatch.setitem(sys.modules, "tiktoken", fake)
    assert tokens.get_exact_counter()("a b c") == 3
