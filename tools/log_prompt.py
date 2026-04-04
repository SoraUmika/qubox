"""log_prompt.py — Agent prompt logging utility.

Writes a timestamped markdown log file to past_prompt/ for every completed
agent task.  Never overwrites an existing file — appends a counter suffix
if there is a filename collision.

Usage
-----
    python tools/log_prompt.py \\
        --task "add-t2-ramsey-experiment" \\
        --prompt "Add a T2 Ramsey experiment class..." \\
        --response "Created qubox/experiments/time_domain/ramsey.py..." \\
        --files "qubox/experiments/time_domain/ramsey.py, API_REFERENCE.md"

    # Interactive mode (reads prompt and response from stdin)
    python tools/log_prompt.py --task "my-task" --interactive

    # From files
    python tools/log_prompt.py \\
        --task "my-task" \\
        --prompt-file prompt.txt \\
        --response-file response.txt
"""
from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

PAST_PROMPT_DIR = Path(__file__).resolve().parent.parent / "past_prompt"

LOG_TEMPLATE = """\
# Prompt Log

**Date:** {date}
**Task:** {task}
**Target files:** {files}

## Original Request

{prompt}

## Response / Changes Made

{response}

## Context

{context}

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
"""


def _safe_filename(base: Path) -> Path:
    """Return *base* if it does not exist, otherwise append _2, _3, ... until unique."""
    if not base.exists():
        return base
    stem   = base.stem
    suffix = base.suffix
    parent = base.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def write_log(
    task: str,
    prompt: str,
    response: str,
    *,
    files: str = "",
    context: str = "",
    dest_dir: Path = PAST_PROMPT_DIR,
    timestamp: datetime.datetime | None = None,
) -> Path:
    """Write a prompt log file.

    Parameters
    ----------
    task
        Short hyphen-separated task name, e.g. ``"add-t2-ramsey-experiment"``.
    prompt
        Original user prompt / request text.
    response
        Summary of what the agent did.
    files
        Comma-separated list of files changed.
    context
        Optional background context.
    dest_dir
        Directory to write into. Defaults to ``past_prompt/``.
    timestamp
        Datetime to use. Defaults to ``datetime.datetime.now()``.

    Returns
    -------
    Path
        Path of the written file.
    """
    if timestamp is None:
        timestamp = datetime.datetime.now()

    date_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
    file_ts  = timestamp.strftime("%Y-%m-%d_%H-%M-%S")

    safe_task = task.lower().replace(" ", "-")
    filename  = f"{file_ts}_{safe_task}.md"

    dest_dir.mkdir(parents=True, exist_ok=True)
    path = _safe_filename(dest_dir / filename)

    content = LOG_TEMPLATE.format(
        date=date_str,
        task=task,
        files=files or "(not specified)",
        prompt=prompt.strip() if prompt.strip() else "(not provided)",
        response=response.strip() if response.strip() else "(not provided)",
        context=context.strip() if context.strip() else "(none)",
    )

    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _read_stdin_block(label: str) -> str:
    print(f"Enter {label} (end with a line containing only '---'):", file=sys.stderr)
    lines = []
    for line in sys.stdin:
        if line.rstrip() == "---":
            break
        lines.append(line)
    return "".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Log an agent prompt and response to past_prompt/.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--task",
        required=True,
        help="Short task name, e.g. 'add-t2-ramsey-experiment'.",
    )
    parser.add_argument(
        "--prompt",
        default="",
        help="Original user prompt text.",
    )
    parser.add_argument(
        "--response",
        default="",
        help="Summary of agent response / changes made.",
    )
    parser.add_argument(
        "--files",
        default="",
        help="Comma-separated list of files changed.",
    )
    parser.add_argument(
        "--context",
        default="",
        help="Optional background context.",
    )
    parser.add_argument(
        "--prompt-file",
        type=Path,
        default=None,
        help="Read prompt text from a file instead of --prompt.",
    )
    parser.add_argument(
        "--response-file",
        type=Path,
        default=None,
        help="Read response text from a file instead of --response.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Read prompt and response interactively from stdin.",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=PAST_PROMPT_DIR,
        help=f"Destination directory. Default: {PAST_PROMPT_DIR}",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    prompt   = args.prompt
    response = args.response

    if args.prompt_file:
        if not args.prompt_file.exists():
            print(f"[ERROR] --prompt-file not found: {args.prompt_file}", file=sys.stderr)
            return 1
        prompt = args.prompt_file.read_text(encoding="utf-8")

    if args.response_file:
        if not args.response_file.exists():
            print(f"[ERROR] --response-file not found: {args.response_file}", file=sys.stderr)
            return 1
        response = args.response_file.read_text(encoding="utf-8")

    if args.interactive:
        prompt   = _read_stdin_block("prompt")
        response = _read_stdin_block("response")

    try:
        path = write_log(
            task=args.task,
            prompt=prompt,
            response=response,
            files=args.files,
            context=args.context,
            dest_dir=args.dest,
        )
        print(f"[OK] Prompt log written: {path}")
        return 0
    except Exception as exc:
        print(f"[ERROR] Failed to write prompt log: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
