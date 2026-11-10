"""把已经跑完的结果写成一份离线 HTML。

  python -m tools.export_report --run <id 或目录> --out report.html --lang zh-CN
  python -m tools.export_report --a <id> --b <id> --out compare.html
  python -m tools.export_report --run <id> --calibration calibration.json --lang en

CSS 和 SVG 都在文件里。没有要去加载的网络地址。不新开模拟，不改种子，不改 AI。

Write one self-contained HTML report from a finished run, an optional combat
comparison, and an optional calibration or gap-triage JSON. Inline CSS and
SVG. No network loads.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sts2sim.htmlreport import main

if __name__ == "__main__":
    raise SystemExit(main())
