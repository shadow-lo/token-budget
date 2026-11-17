from token_budget.gitignore import GitIgnore, IgnoreStack


def ign(text, rel, is_dir=False):
    return IgnoreStack().extended("", GitIgnore(text)).is_ignored(rel, is_dir)


def test_basic_glob_and_comments():
    text = "# comment\n\n*.log\n"
    assert ign(text, "a.log")
    assert ign(text, "sub/dir/a.log")
    assert not ign(text, "a.txt")


def test_dir_only_rule():
    assert ign("build/\n", "build", True)
    assert not ign("build/\n", "build", False)
    assert not ign("build/\n", "src/build.py")


def test_anchored_rule():
    assert ign("/root.txt\n", "root.txt")
    assert not ign("/root.txt\n", "sub/root.txt")
    assert ign("docs/*.md\n", "docs/a.md")
    assert not ign("docs/*.md\n", "x/docs/a.md")


def test_double_star():
    assert ign("a/**/z.txt\n", "a/z.txt")
    assert ign("a/**/z.txt\n", "a/b/c/z.txt")
    assert ign("logs/**\n", "logs/x/y.txt")
    assert ign("**/tmp\n", "x/y/tmp", True)


def test_negation():
    text = "*.log\n!keep.log\n"
    assert ign(text, "a.log")
    assert not ign(text, "keep.log")


def test_question_and_class():
    assert ign("f?.txt\n", "fa.txt")
    assert not ign("f?.txt\n", "fab.txt")
    assert ign("[ab].txt\n", "a.txt")
    assert ign("[!ab].txt\n", "c.txt")
    assert not ign("[!ab].txt\n", "a.txt")
    assert ign("[oops\n", "[oops")


def test_escapes():
    assert ign("\\#file\n", "#file")
    assert ign("\\!file\n", "!file")


def test_nested_gitignore_layers():
    stack = IgnoreStack().extended("sub", GitIgnore("*.tmp\n"))
    assert stack.is_ignored("sub/a.tmp", False)
    assert not stack.is_ignored("a.tmp", False)
    assert not stack.is_ignored("other/a.tmp", False)


def test_blank_and_slash_only_lines_ignored():
    assert not ign("/\n   \n", "anything")
