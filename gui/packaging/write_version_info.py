"""Write the PyInstaller Windows version resource from sts2sim.__version__."""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from sts2sim.version import read_project_version, version_info_text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--version", default="", help="override; default is sts2sim.__version__")
    args = ap.parse_args(argv)
    version = args.version.strip() or read_project_version(ROOT)
    text = version_info_text(version)
    parent = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(parent, exist_ok=True)
    with open(args.out, "w", encoding="ascii", newline="\n") as handle:
        handle.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
