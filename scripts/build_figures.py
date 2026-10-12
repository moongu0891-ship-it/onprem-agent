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


W = 1808   # .page 1720 + 여백
# 한 줄로 보이게: 넘치는 상자는 그 안 글자를 조금씩 줄인다(실제 그린 폭으로 잰다). 안쪽 상자부터.
FIT_JS = """() => {
  const els = [...document.querySelectorAll('.box, .band, .pill, .term, .kv, .nav .box')];
  els.sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);
  for (const b of els) {
    let guard = 40;
    while (b.scrollWidth > b.clientWidth + 1 && guard--) {
      const ts = [b, ...b.querySelectorAll('*')];
      let moved = false;
      for (const t of ts) { const fs = parseFloat(getComputedStyle(t).fontSize); if (fs > 9.5) { t.style.fontSize = (fs * 0.96) + 'px'; moved = true; } }
      if (!moved) break;
    }
  }
}"""
LEFT_JS = """() => [...document.querySelectorAll('.box, .band, .pill, .term')].filter(e => e.scrollWidth > e.clientWidth + 1)
  .map(e => (e.innerText || '').slice(0, 50).replace(/\\n/g, ' '))"""


def main():
    from playwright.sync_api import sync_playwright
    from pypdf import PdfWriter
    OUT.mkdir(exist_ok=True)
    pages = sorted(p for p in SRC.glob("*.html"))
    pdfs = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": 1000}, device_scale_factor=2)
        for p in pages:
            pg.goto(p.resolve().as_uri())
            pg.wait_for_timeout(300)
            pg.evaluate(FIT_JS)
            for x in pg.evaluate(LEFT_JS):
                print("  넘침:", x)
            h = pg.evaluate("document.documentElement.scrollHeight")
            out = OUT / (p.stem + ".pdf")
            pg.pdf(path=str(out), width=f"{W}px", height=f"{h + 2}px", print_background=True, margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
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
