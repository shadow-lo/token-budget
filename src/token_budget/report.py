"""Build and render the report (text and JSON)."""

from collections import defaultdict
from typing import Dict, List, Optional

from .scanner import ScanResult

BAR_WIDTH = 24
GREEN, RED, DIM, BOLD, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


def by_directory(result: ScanResult, depth: int = 1) -> List[dict]:
    totals: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
    for f in result.files:
        parts = f.path.split("/")[:-1][:depth]
        key = "/".join(parts) + "/" if parts else "./"
        totals[key][0] += f.tokens
        totals[key][1] += 1
    rows = [{"dir": d, "tokens": t, "files": n} for d, (t, n) in totals.items()]
    rows.sort(key=lambda r: (-r["tokens"], r["dir"]))
    return rows


def build(result: ScanResult, limit: Optional[int], top: int, depth: int,
          exact: bool) -> dict:
    total = result.total_tokens
    data = {
        "root": result.root,
        "mode": "exact (tiktoken cl100k_base)" if exact else "estimate (~4 chars/token)",
        "approximate": not exact,
        "total_tokens": total,
        "file_count": len(result.files),
        "limit": limit,
        "percent": None,
        "fits": None,
        "top_files": [{"path": f.path, "tokens": f.tokens} for f in result.files[:top]],
        "directories": by_directory(result, depth),
        "skipped": {"total": result.skipped_total, "reasons": dict(result.skipped)},
    }
    if limit:
        data["percent"] = round(total / limit * 100, 1)
        data["fits"] = total <= limit
    return data


def _num(n: int, approx: bool) -> str:
    return ("~" if approx else "") + f"{n:,}"


def _bar(value: int, biggest: int) -> str:
    if biggest <= 0:
        return ""
    return "█" * max(1, round(value / biggest * BAR_WIDTH)) if value else ""


def render(data: dict, color: bool = False) -> str:
    def c(code: str, text: str) -> str:
        return f"{code}{text}{RESET}" if color else text

    approx = data["approximate"]
    lines = [
        f"{c(BOLD, 'Folder:')} {data['root']}    "
        f"{c(BOLD, 'Total:')} {_num(data['total_tokens'], approx)} tokens "
        f"({data['file_count']} files)"
    ]
    if data["limit"]:
        ok = data["fits"]
        mark = c(GREEN, "✅ fits") if ok else c(RED, "❌ does not fit")
        lines.append(
            f"Limit:  {data['limit']:,}    Usage: {data['percent']}%  {mark}"
        )
    lines.append(c(DIM, f"Mode:   {data['mode']}"))

    top = data["top_files"]
    if top:
        lines += ["", c(BOLD, f"Top {len(top)} files")]
        biggest = top[0]["tokens"]
        width = max(len(_num(f["tokens"], approx)) for f in top)
        for f in top:
            lines.append(
                f"  {_num(f['tokens'], approx):>{width}}  {f['path']}  "
                + c(GREEN, _bar(f["tokens"], biggest))
            )

    dirs = data["directories"]
    if dirs:
        lines += ["", c(BOLD, "By directory")]
        biggest = dirs[0]["tokens"]
        width = max(len(_num(d["tokens"], approx)) for d in dirs)
        for d in dirs:
            lines.append(
                f"  {_num(d['tokens'], approx):>{width}}  {d['dir']} ({d['files']})  "
                + c(GREEN, _bar(d["tokens"], biggest))
            )

    sk = data["skipped"]
    if sk["total"]:
        reasons = ", ".join(f"{n} {r}" for r, n in sorted(sk["reasons"].items()))
        lines += ["", f"Skipped: {sk['total']:,} files ({reasons})"]
    if approx:
        lines += ["", c(DIM, "~ = estimate; real counts depend on the model's tokenizer.")]
    return "\n".join(lines)
