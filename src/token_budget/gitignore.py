"""A small .gitignore matcher (stdlib only).

Supports comments, negation (!), anchoring (leading or inner /), directory-only
rules (trailing /), `*`, `?`, `[...]` and `**`. Not supported: .git/info/exclude
and the global excludes file.
"""

import re
from typing import List, Optional, Tuple


def _translate(pattern: str) -> str:
    """Translate one gitignore glob (without anchors) into a regex body."""
    i, n = 0, len(pattern)
    out = []
    while i < n:
        c = pattern[i]
        if c == "*":
            if pattern[i : i + 2] == "**":
                i += 2
                if pattern[i : i + 1] == "/":
                    i += 1
                    out.append("(?:.*/)?")  # "**/" = zero or more directories
                else:
                    out.append(".*")
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            j = pattern.find("]", i + 2)
            if j == -1:
                out.append(re.escape(c))
            else:
                body = pattern[i + 1 : j]
                if body and body[0] == "!":
                    body = "^" + body[1:]
                out.append("[" + body.replace("\\", "\\\\") + "]")
                i = j
        elif c == "\\" and i + 1 < n:
            i += 1
            out.append(re.escape(pattern[i]))
        else:
            out.append(re.escape(c))
        i += 1
    return "".join(out)


class Rule:
    def __init__(self, line: str):
        self.negate = False
        self.dir_only = False
        self.regex: Optional["re.Pattern[str]"] = None
        line = line.rstrip("\n").rstrip("\r")
        if not line.strip() or line.startswith("#"):
            return
        # trailing spaces are ignored unless escaped
        stripped = line.rstrip(" ")
        if stripped.endswith("\\") and len(stripped) < len(line):
            stripped += " "
        line = stripped
        if line.startswith("\\#") or line.startswith("\\!"):
            line = line[1:]
        elif line.startswith("!"):
            self.negate = True
            line = line[1:]
        if line.endswith("/"):
            self.dir_only = True
            line = line.rstrip("/")
        if not line:
            return
        anchored = "/" in line
        line = line.lstrip("/")
        body = _translate(line)
        prefix = "^" if anchored else "^(?:.*/)?"
        self.regex = re.compile(prefix + body + "$")

    def matches(self, rel: str, is_dir: bool) -> bool:
        if self.regex is None:
            return False
        if self.dir_only and not is_dir:
            return False
        return self.regex.match(rel) is not None


class GitIgnore:
    """Rules from one .gitignore file, relative to the directory holding it."""

    def __init__(self, text: str):
        self.rules: List[Rule] = [r for r in map(Rule, text.splitlines()) if r.regex]

    def verdict(self, rel: str, is_dir: bool) -> Optional[bool]:
        """True = ignored, False = re-included, None = no rule matched."""
        result = None
        for rule in self.rules:
            if rule.matches(rel, is_dir):
                result = not rule.negate
        return result


class IgnoreStack:
    """The chain of .gitignore files from the scan root down to a directory."""

    def __init__(self, layers: Optional[List[Tuple[str, GitIgnore]]] = None):
        self.layers = layers or []

    def extended(self, base: str, gi: GitIgnore) -> "IgnoreStack":
        return IgnoreStack(self.layers + [(base, gi)])

    def is_ignored(self, rel: str, is_dir: bool) -> bool:
        """`rel` is a posix path relative to the scan root. Deeper files win."""
        result = False
        for base, gi in self.layers:
            if base:
                if not rel.startswith(base + "/"):
                    continue
                sub = rel[len(base) + 1 :]
            else:
                sub = rel
            v = gi.verdict(sub, is_dir)
            if v is not None:
                result = v
        return result
