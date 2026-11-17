"""Walk a directory and count tokens per file."""

import fnmatch
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

from .gitignore import GitIgnore, IgnoreStack
from .tokens import count_file

DEFAULT_SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".idea",
}

BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tiff", ".psd",
    ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".jar", ".whl",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a", ".class", ".pyc", ".pyd",
    ".mp3", ".wav", ".ogg", ".flac", ".mp4", ".mov", ".avi", ".mkv", ".webm",
    ".ttf", ".otf", ".woff", ".woff2", ".eot", ".sqlite", ".db", ".lock",
}


@dataclass
class FileStat:
    path: str  # posix, relative to the scan root
    tokens: int


@dataclass
class ScanResult:
    root: str
    files: List[FileStat] = field(default_factory=list)
    skipped: Dict[str, int] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return sum(f.tokens for f in self.files)

    @property
    def skipped_total(self) -> int:
        return sum(self.skipped.values())

    def skip(self, reason: str, n: int = 1) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + n


def is_binary(path: str) -> bool:
    """Known binary extension, or a NUL byte in the first 8 KB."""
    if os.path.splitext(path)[1].lower() in BINARY_EXTS:
        return True
    try:
        with open(path, "rb") as fh:
            return b"\0" in fh.read(8192)
    except OSError:
        return False


def _excluded(rel: str, patterns: Sequence[str]) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return any(
        fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(name, p) for p in patterns
    )


def _read_ignore(directory: str) -> Optional[GitIgnore]:
    try:
        with open(os.path.join(directory, ".gitignore"), encoding="utf-8",
                  errors="replace") as fh:
            return GitIgnore(fh.read())
    except OSError:
        return None


def _count_dir_tree(dirpath: str) -> int:
    """Count files in a skipped directory (for the 'skipped' tally)."""
    total = 0
    for _, _, names in os.walk(dirpath, followlinks=False):
        total += len(names)
    return total


def scan(
    root: str,
    exts: Optional[Sequence[str]] = None,
    excludes: Sequence[str] = (),
    use_gitignore: bool = True,
    counter: Optional[Callable[[str], int]] = None,
) -> ScanResult:
    """Scan `root` (a directory or a single file)."""
    result = ScanResult(root=root)
    exts_norm = (
        {e.lower() if e.startswith(".") else "." + e.lower() for e in exts}
        if exts else None
    )

    def handle_file(full: str, rel: str) -> None:
        if os.path.islink(full):
            result.skip("symlink")
            return
        if exts_norm is not None and os.path.splitext(full)[1].lower() not in exts_norm:
            result.skip("filtered (--ext)")
            return
        if is_binary(full):
            result.skip("binary")
            return
        try:
            tokens = count_file(full, counter)
        except OSError:
            result.skip("unreadable")
            return
        result.files.append(FileStat(rel, tokens))

    if os.path.isfile(root):
        handle_file(root, os.path.basename(root))
        return result

    stack = IgnoreStack()
    if use_gitignore:
        gi = _read_ignore(root)
        if gi:
            stack = stack.extended("", gi)
    # (directory, relative path, ignore stack)
    pending = [(root, "", stack)]
    while pending:
        directory, rel_dir, stack = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda e: e.name)
        except OSError:
            result.skip("unreadable")
            continue
        for entry in entries:
            rel = f"{rel_dir}/{entry.name}" if rel_dir else entry.name
            is_dir = entry.is_dir(follow_symlinks=False)
            if is_dir:
                if entry.name in DEFAULT_SKIP_DIRS or _excluded(rel, excludes) or (
                    use_gitignore and stack.is_ignored(rel, True)
                ):
                    result.skip("ignored (.gitignore, excluded, node_modules, ...)",
                                _count_dir_tree(entry.path))
                    continue
                sub = stack
                if use_gitignore:
                    gi = _read_ignore(entry.path)
                    if gi:
                        sub = stack.extended(rel, gi)
                pending.append((entry.path, rel, sub))
            else:
                if _excluded(rel, excludes) or (
                    use_gitignore and stack.is_ignored(rel, False)
                ):
                    result.skip("ignored (.gitignore, excluded, node_modules, ...)")
                    continue
                handle_file(entry.path, rel)
    result.files.sort(key=lambda f: (-f.tokens, f.path))
    return result
