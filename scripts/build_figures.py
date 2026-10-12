"""docs/figures/*.html 을 PDF 한 묶음으로 — 한 장에 그림 하나(높이는 내용에 맞춤).

    python scripts/build_figures.py                 → docs/온프레미스_에이전트_그림.pdf
    python scripts/build_figures.py --png           → docs/figures/out/*.png 미리보기도
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs/figures"
OUT = SRC / "out"


def main():
    from playwright.sync_api import sync_playwright
    from pypdf import PdfWriter
    OUT.mkdir(exist_ok=True)
    pages = sorted(p for p in SRC.glob("*.html"))
    pdfs = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1480, "height": 1000}, device_scale_factor=2)
        for p in pages:
            pg.goto(p.resolve().as_uri())
            pg.wait_for_timeout(300)
            h = pg.evaluate("document.documentElement.scrollHeight")
            out = OUT / (p.stem + ".pdf")
            pg.pdf(path=str(out), width="1480px", height=f"{h + 2}px", print_background=True, margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
            if "--png" in sys.argv:
                pg.screenshot(path=str(OUT / (p.stem + ".png")), full_page=True)
            pdfs.append(out)
            print(f"{p.name}: {h}px")
        b.close()
    w = PdfWriter()
    for f in pdfs:
        w.append(str(f))
    target = ROOT / "docs/온프레미스_에이전트_그림.pdf"
    w.write(str(target))
    print("저장:", target.relative_to(ROOT), f"({len(pdfs)}장)")


if __name__ == "__main__":
    main()
