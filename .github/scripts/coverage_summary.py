"""Write a pytest-cov JSON report into the GitHub Actions job summary.

Nothing is uploaded. When ``GITHUB_STEP_SUMMARY`` is unset, the same
Markdown is printed so the script can be checked locally.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

PACKAGES = ("sts2sim", "gui", "tools")


def package_of(filename: str) -> str:
    parts = [part for part in filename.replace("\\", "/").split("/") if part]
    for name in PACKAGES:
        if name in parts:
            return name
    return "other"


def percent(covered: int, statements: int) -> str:
    if statements <= 0:
        return "n/a"
    return f"{covered * 100 / statements:.1f}%"


def summarize(data: dict) -> str:
    buckets: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for filename, info in data.get("files", {}).items():
        summary = info.get("summary") or {}
        statements = int(summary.get("num_statements") or 0)
        covered = int(summary.get("covered_lines") or 0)
        row = buckets[package_of(filename)]
        row[0] += statements
        row[1] += covered

    totals = data.get("totals") or {}
    total_statements = int(totals.get("num_statements") or 0)
    total_covered = int(totals.get("covered_lines") or 0)
    lines = [
        "### Coverage",
        "",
        "pytest-cov for `sts2sim`, `gui`, and `tools`.",
        "The table is this job's summary only; nothing is uploaded.",
        "",
        "| Package | Statements | Covered | Missing | Coverage |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name in PACKAGES:
        statements, covered = buckets.get(name, [0, 0])
        missing = statements - covered
        lines.append(
            f"| `{name}` | {statements} | {covered} | {missing} | {percent(covered, statements)} |"
        )
    other = buckets.get("other")
    if other and other[0]:
        statements, covered = other
        missing = statements - covered
        lines.append(
            f"| other | {statements} | {covered} | {missing} | {percent(covered, statements)} |"
        )
    total_missing = total_statements - total_covered
    lines.append(
        f"| **Total** | {total_statements} | {total_covered} | {total_missing} | "
        f"{percent(total_covered, total_statements)} |"
    )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else "coverage.json"
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            text = summarize(json.load(handle))
    else:
        text = "### Coverage\n\nCoverage report was not produced.\n"
    destination = os.environ.get("GITHUB_STEP_SUMMARY")
    if destination:
        with open(destination, "a", encoding="utf-8") as handle:
            handle.write(text)
            if not text.endswith("\n"):
                handle.write("\n")
    else:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
