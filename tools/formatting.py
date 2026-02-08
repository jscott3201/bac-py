"""Output formatting for the BACnet CLI.

Supports table (human-readable) and JSON output modes.
"""

from __future__ import annotations

import json
import sys
from typing import Any


def print_table(
    headers: list[str],
    rows: list[list[Any]],
) -> None:
    """Print aligned columns with separator lines."""
    # Compute column widths
    str_rows = [[str(v) for v in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in str_rows:
        for i, val in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(val))

    # Header
    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sep = "  ".join("-" * w for w in widths)
    print(header_line)
    print(sep)

    # Rows
    for row in str_rows:
        line = "  ".join(
            (row[i] if i < len(row) else "").ljust(widths[i]) for i in range(len(headers))
        )
        print(line)


def print_json(data: Any) -> None:
    """Print data as formatted JSON."""
    print(json.dumps(data, indent=2, default=str))


def print_error(message: str, use_json: bool = False) -> None:
    """Print an error message, respecting output mode."""
    if use_json:
        print(json.dumps({"error": message}))
    else:
        print(f"Error: {message}", file=sys.stderr)


def print_kv(pairs: list[tuple[str, Any]]) -> None:
    """Print key-value pairs aligned on the colon."""
    if not pairs:
        return
    max_key = max(len(k) for k, _ in pairs)
    for key, value in pairs:
        print(f"  {key.ljust(max_key)}  {value}")
