"""docs/클라우드_실습_워크북.md → 책 모양 PDF (docs/클라우드_실습_워크북.pdf). 'Minikube에서 AWS EKS까지' 워크북과 같은 꼴 —
장마다 완료 목표 → 그림 → 실행(명령 상자, 행 번호) → 관찰 → 장애·복구 → 정리 → 성공 확인. 표지와 차례를 앞에 붙인다.

    python scripts/build_workbook.py [docs/클라우드_실습_워크북.md] [출력 .pdf]
"""
from __future__ import annotations

import html
import re
import sys
from datetime import date
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs/클라우드_실습_워크북.md"
DST = Path(sys.argv[2]) if len(sys.argv) > 2 else SRC.with_suffix(".pdf")
SUBTITLE = {"클라우드_실습_워크북": "8주차 · 환경: Windows 11 · WSL2 Ubuntu · Docker · minikube(docker 드라이버) · RTX 5070 Laptop 8GB<br>형식: 장마다 완료 목표 → 그림 → 실행(명령 상자 · 행별 해설) → 관찰 → 장애·복구 → 정리 → 성공 확인 — 그리고 잰다",
            "설계서": "시스템 설계서 · 목적 → 전체 구조 → 상담 화면 → 에이전트 그래프 → 데이터 → 흐름 → 시험 → 배포 → 보안 → 한계<br>숫자는 모두 노트북(RTX 5070 Laptop 8GB)에서 잰 것 · 측정 원본 reports/"}.get(SRC.stem, "")

CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }
*{box-sizing:border-box}
body{font-family:"Noto Sans CJK KR","Noto Sans KR",sans-serif;font-size:10.5pt;line-height:1.55;color:#1d2433;margin:0}
.cover{height:257mm;display:flex;flex-direction:column;justify-content:center;page-break-after:always;border-left:14px solid #1b6fb8;padding-left:28px}
.cover h1{font-size:30pt;margin:0 0 10px;line-height:1.25}
.cover .sub{font-size:14pt;color:#5b6472;margin:0 0 30px}
.cover .meta{font-size:10.5pt;color:#5b6472;line-height:1.9}
.toc{page-break-after:always}
.toc h2{font-size:18pt;border-bottom:2px solid #1b6fb8;padding-bottom:4px}
.toc ol{list-style:none;padding:0;margin:0;columns:1}
.toc li{padding:3px 0;border-bottom:1px dotted #c9d0da;font-size:11pt}
.toc li span{color:#5b6472;font-size:9.5pt;margin-left:8px}
h1{font-size:20pt;margin:0 0 8px;color:#1d2433}
h2{font-size:16pt;color:#1b6fb8;margin:0 0 10px;padding:6px 0 6px 12px;border-left:6px solid #1b6fb8;background:#f3f8fe;page-break-before:always;page-break-after:avoid}
h2.first{page-break-before:auto}
h3{font-size:12.5pt;color:#0f8b8d;margin:16px 0 6px;page-break-after:avoid}
p{margin:6px 0}
strong{color:#1d2433}
code{font-family:"DejaVu Sans Mono","Noto Sans Mono CJK KR",monospace;font-size:9pt;background:#eef1f5;padding:1px 4px;border-radius:3px}
pre{background:#13202e;color:#d8e2ee;border-radius:8px;padding:10px 12px;font-family:"DejaVu Sans Mono","Noto Sans Mono CJK KR",monospace;font-size:9pt;line-height:1.6;white-space:pre-wrap;page-break-inside:avoid;margin:8px 0}
pre code{background:none;color:inherit;padding:0;font-size:inherit}
pre.fig{background:#f5f6f8;color:#1d2433;border:1px solid #c9d0da;white-space:pre;font-size:7.6pt;line-height:1.45;overflow:hidden}
del{color:#9aa3b2}
pre.fig.wide{font-size:6pt;line-height:1.4}
pre .lead{color:#8fd3ff;font-weight:700;display:block;border-bottom:1px solid #2b3d52;margin-bottom:6px;padding-bottom:4px}
pre .ln{color:#ffd166;display:inline-block;width:2.2em;text-align:right;margin-right:10px}
table{border-collapse:collapse;width:100%;font-size:9.3pt;margin:8px 0;page-break-inside:auto}
th,td{border:1px solid #c9d0da;padding:4px 6px;vertical-align:top;text-align:left}
th{background:#eef1f5;font-weight:700}
tr{page-break-inside:avoid}
blockquote{border-left:4px solid #d97a06;margin:8px 0;padding:4px 10px;background:#fff8ee}
hr{border:0;border-top:1px solid #c9d0da;margin:14px 0}
em{font-style:normal;color:#5b6472}
a{color:#1b6fb8;text-decoration:none}
ul,ol{margin:4px 0 4px 20px;padding:0}
li{margin:2px 0}
.step{font-weight:700;color:#1b6fb8}
"""

BOX = re.compile(r"^ (Ubuntu Bash) \| (\d\d-\d\d\d)\s*(.*)$")


def render_code(block: str) -> str:
    lines = block.split("\n")
    m = BOX.match(lines[0]) if lines else None
    if m:
        out = [f'<span class="lead">{html.escape(lines[0].strip())}</span>']
        for ln in lines[1:]:
            mm = re.match(r"^\s*(\d+)\s{2}(.*)$", ln)
            if mm:
                out.append(f'<span class="ln">{mm.group(1)}</span>{html.escape(mm.group(2))}')
            else:
                out.append(html.escape(ln))
        return "<pre>" + "\n".join(out) + "</pre>"
    # 그림(글자 그림)과 그 밖의 출력 — 줄을 꺾지 않고 작게, 밝은 바탕
    wide = max((len(ln) for ln in lines), default=0) > 100
    return f'<pre class="fig{" wide" if wide else ""}">' + html.escape(block) + "</pre>"


def main():
    text = SRC.read_text(encoding="utf-8")
    # 코드 상자를 먼저 떼어 두고(마크다운 변환이 건드리지 않게) 자리표로 바꾼다
    blocks: list[str] = []

    def stash(m):
        blocks.append(m.group(1).rstrip("\n"))
        return f"\n\n@@CODE{len(blocks) - 1}@@\n\n"

    text = re.sub(r"```[a-z]*\n(.*?)```", stash, text, flags=re.S)
    # 'N행 …' 해설 줄 앞머리를 굵게
    text = re.sub(r"^(\d+(?:~\d+)?행)\s", r"<span class=\"step\">\1</span> ", text, flags=re.M)
    body = markdown.markdown(text, extensions=["tables", "sane_lists", "pymdownx.tilde"])
    for i, b in enumerate(blocks):
        body = body.replace(f"<p>@@CODE{i}@@</p>", render_code(b)).replace(f"@@CODE{i}@@", render_code(b))
    # 차례: ## 제목들
    heads = re.findall(r"<h2>(.*?)</h2>", body)
    body = body.replace("<h2>", '<h2 class="first">', 1)
    title = re.search(r"<h1>(.*?)</h1>", body)
    title_text = re.sub(r"<.*?>", "", title.group(1)) if title else SRC.stem
    body = body.replace(title.group(0), "", 1) if title else body
    toc = "".join(f"<li>{re.sub(r'<.*?>', '', h)}</li>" for h in heads)
    commit = ""
    try:
        import subprocess
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    except Exception:
        pass
    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{html.escape(title_text)}</title><style>{CSS}</style></head><body>
<div class="cover"><h1>{html.escape(title_text)}</h1><p class="sub">온프레미스 에이전트를 안전하게 만들고, 재서 고르는 프레임워크</p>
<p class="meta">{SUBTITLE}<br>
저장소: github.com/moongu0891-ship-it/onprem-agent · 커밋 {commit} · {date.today().isoformat()}</p></div>
<div class="toc"><h2>차례</h2><ol>{toc}</ol></div>
{body}</body></html>"""
    tmp = DST.with_suffix(".html")
    tmp.write_text(page, encoding="utf-8")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page()
        pg.goto(tmp.resolve().as_uri())
        pg.wait_for_timeout(500)
        pg.pdf(path=str(DST), format="A4", print_background=True, prefer_css_page_size=True,
               display_header_footer=True, header_template="<div></div>",
               footer_template='<div style="font-size:8px;color:#5b6472;width:100%;text-align:center;font-family:sans-serif">'
                               f'{html.escape(title_text)} · <span class="pageNumber"></span> / <span class="totalPages"></span></div>')
        b.close()
    tmp.unlink()
    print("저장:", DST)


if __name__ == "__main__":
    main()
