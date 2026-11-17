"""Command line interface."""

import argparse
import json
import os
import sys
from typing import List, Optional

from . import __version__
from .report import build, render
from .scanner import scan
from .tokens import MODEL_LIMITS, get_exact_counter


def _csv(value: str) -> List[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="token-budget",
        description="Estimate how many LLM tokens a folder holds and whether "
        "it fits a context window. Fully offline.",
        epilog="Exit codes: 0 ok / fits, 1 does not fit the limit, 2 error.",
    )
    p.add_argument("path", nargs="?", default=".", help="folder or file (default: .)")
    p.add_argument("--model", choices=sorted(MODEL_LIMITS),
                   help="use a nominal context window for this model family")
    p.add_argument("--limit", type=int, help="context window size in tokens")
    p.add_argument("--top", type=int, default=10, help="show the N largest files (default 10)")
    p.add_argument("--depth", type=int, default=1, help="directory breakdown depth (default 1)")
    p.add_argument("--ext", type=_csv, help="only these extensions, e.g. .py,.md")
    p.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                   help="skip paths matching GLOB (repeatable, or comma-separated)")
    p.add_argument("--no-gitignore", action="store_true", help="do not read .gitignore files")
    p.add_argument("--exact", action="store_true",
                   help="use tiktoken (pip install 'token-budget[exact]')")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--no-color", action="store_true", help="disable colored output")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _use_color(args: argparse.Namespace) -> bool:
    if args.no_color or "NO_COLOR" in os.environ or args.json:
        return False
    return sys.stdout.isatty()


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    args = build_parser().parse_args(argv)
    if not os.path.exists(args.path):
        print(f"token-budget: no such path: {args.path}", file=sys.stderr)
        return 2
    if args.limit is not None and args.limit <= 0:
        print("token-budget: --limit must be positive", file=sys.stderr)
        return 2
    limit = args.limit if args.limit is not None else MODEL_LIMITS.get(args.model or "")

    counter = None
    if args.exact:
        try:
            counter = get_exact_counter()
        except RuntimeError as exc:
            print(f"token-budget: {exc}", file=sys.stderr)
            return 2

    excludes = [x for item in args.exclude for x in _csv(item)]
    result = scan(args.path, exts=args.ext, excludes=excludes,
                  use_gitignore=not args.no_gitignore, counter=counter)
    data = build(result, limit, max(args.top, 0), max(args.depth, 1), args.exact)

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        if os.name == "nt" and _use_color(args):
            os.system("")  # enables ANSI escapes in Windows terminals
        print(render(data, color=_use_color(args)))
    return 1 if data["fits"] is False else 0
