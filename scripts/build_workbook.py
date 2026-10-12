"""마크다운 문서 → 책 모양 PDF. 워크북과 설계서가 쓴다.

    python scripts/build_workbook.py                          → docs/클라우드_실습_워크북.pdf
    python scripts/build_workbook.py docs/설계서.md            → docs/설계서.pdf
    python scripts/build_workbook.py … --html                 → 같은 이름 .html 도 남김(미리보기)

- 글자 그림(```` ``` ```` 안의 '그림 NN | 제목')은 docs/figures/book/NN.html 의 도식으로 바꿔 넣는다.
- 'Ubuntu Bash | NN-NNN' 상자는 행 번호가 있는 명령 상자(입력)로, 바로 뒤 '결과 | NN-NNN | 실제…/기대…' 상자는
  그 밑에 붙는 결과 상자로(같은 행 번호 · 마지막 '✔ 확인:' 줄). 'N행 …' 해설은 번호 표로.
- 명령 · 결과 · 표 · 그림 글자는 한 줄로 — 넘치면 인쇄 폭(182mm)에서 재서 글자를 줄인다(FIT_JS).
- **완료 목표** · **관찰** · **장애·복구** · **정리** · **성공 확인** · **예상/잰다** 문단은 색 상자로.
- ### 실제 클라우드에서는 / 연습 / 이해 확인 / 면접 절은 각자의 상자로.
- 모양은 docs/figures/book/book.css.
"""
from __future__ import annotations

import html
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import markdown
from bs4 import BeautifulSoup, NavigableString

ROOT = Path(__file__).resolve().parents[1]
args = [a for a in sys.argv[1:] if not a.startswith("--")]
SRC = Path(args[0]) if args else ROOT / "docs/클라우드_실습_워크북.md"
DST = Path(args[1]) if len(args) > 1 else SRC.with_suffix(".pdf")
FIG = ROOT / "docs/figures/book"
DB = ('<svg class="ic" viewBox="0 0 16 18"><ellipse cx="8" cy="3.5" rx="6.5" ry="2.5"/>'
      '<path d="M1.5 3.5v11c0 1.4 2.9 2.5 6.5 2.5s6.5-1.1 6.5-2.5v-11"/></svg>')

# 문서별 표지
META = {
    "클라우드_실습_워크북": dict(
        kicker="8주차 · 실습 워크북",
        lead="클라우드의 층 — 엣지 · 로드 밸런서 · 오토스케일링 · 게이트웨이 · GPU 모델 서빙 · DB · 관측 · CI/CD · IaC — 을 "
             "노트북 한 대의 minikube 위에 하나씩 설정하고, 망가뜨려 보고, 재면서 익힌다.",
        meta=[("환경", "Windows 11 · WSL2 Ubuntu · Docker · minikube(docker 드라이버) · RTX 5070 Laptop 8GB"),
              ("장마다", "완료 목표 → 그림 → 실행(명령 · 행별 해설) → 관찰 → 장애·복구 → 정리 → 성공 확인"),
              ("익히기", "실제 클라우드(AWS)에서는 · 연습(바꿔 보고 관찰) · 이해 확인 문제 · 면접 질문 — 정답은 부록"),
              ("원본", "docs/클라우드_실습_워크북.md · 측정 원본 reports/cloud_w8.md")],
        stats=[("13장", "클러스터 하나에 층마다 한 장"), ("58초", "GPU 모델 서버 두 번째 시작 (첫 시작 2시간 40분)"),
               ("409 → 200", "Pod 를 죽여도 승인이 이어지게"), ("1분 30초", "make cloud-up 다시 올리기")]),
    "설계서": dict(
        kicker="시스템 설계서",
        lead="회사 안에서만 도는 업무 상담 AI 에이전트 — 무엇을 만들었고, 어떻게 나뉘어 있고, 어디서 무엇을 막고, 어떻게 재는가.",
        meta=[("범위", "설비 정비 · 고객 상담 · IT 헬프데스크 세 창구, 노트북 개발부터 minikube 배포까지"),
              ("근거", "숫자는 모두 노트북(RTX 5070 Laptop 8GB)에서 잰 것 — agent/README · reports/"),
              ("함께", "그림 묶음(온프레미스_에이전트_그림.pdf) · 클라우드 실습 워크북 · 쉽게 풀어쓴 개념")],
        stats=[("92%", "생각 모드 켬, 기존 26과업 (끔 54%)"), ("25/26", "처음 보는 확인용 과업, 두 번"),
               ("0", "위험 행동 · 개인정보 노출 · 거짓 실행 보고"), ("폴더 하나", "새 창구 — 핵심 코드 수정 0줄")]),
}

CALLOUT = [  # (머리말이 이렇게 시작하면, 상자 종류)
    ("완료 목표", "goal"), ("관찰", "obs"), ("장애·복구", "trb"), ("정리", "cln"), ("성공 확인", "ok"),
    ("잰다", "pre"), ("예상", "pre"),
]
SECTION = [  # ### 제목이 이렇게 시작하면, 절 상자 종류
    ("실제 클라우드", "aws"), ("연습", "prac"), ("이해 확인", "quiz"), ("면접", "intv"),
]


def disp_width(s: str) -> int:
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)


def render_code(block: str) -> str:
    lines = block.split("\n")
    first = lines[0].strip() if lines else ""
    m = re.match(r"^결과\s*\|\s*(\d\d-\d\d\d)\s*\|\s*(.*)$", first)
    if m:
        return render_result(m.group(1), m.group(2), lines[1:])
    m = re.match(r"^(Ubuntu Bash)\s*\|\s*(\d\d-\d\d\d)\s*(.*)$", first)
    if m:
        size = fit_size([re.sub(r"^\s*\d+\s{2}", "", x) for x in lines[1:]], 7.5)
        rows = []
        for ln in lines[1:]:
            mm = re.match(r"^\s*(\d+)\s{2}(.*)$", ln)
            no, cmd = (mm.group(1), mm.group(2)) if mm else ("", ln)
            if not cmd.strip() and not no:
                continue
            cmd_h = html.escape(cmd)
            cmd_h = re.sub(r"(\s#\s.*)$", r'<span style="color:#8fa3b8">\1</span>', cmd_h)
            rows.append(f'<tr><td class="ln">{no}</td><td>{cmd_h}</td></tr>')
        note = f'<span class="nt">{html.escape(m.group(3))}</span>' if m.group(3) else ""
        return (f'<div class="term"><div class="hd"><span><b>{m.group(1)}</b>{note}</span>'
                f'<span class="id">{m.group(2)}</span></div><table style="font-size:{size:.2f}pt">{"".join(rows)}</table></div>')
    key, no, title = figure_key(first, block)
    if key and (FIG / f"{key}.html").exists():
        body = (FIG / f"{key}.html").read_text(encoding="utf-8").replace("{DB}", DB)
        return (f'<figure class="dg"><figcaption><span class="fno">{html.escape(no)}</span>{html.escape(title)}</figcaption>'
                f'<div class="dgb">{body}</div></figure>')
    size = fit_size(lines, 7.2, 490)
    return f'<pre class="out" style="font-size:{size:.2f}pt">' + html.escape(block) + "</pre>"


def fit_size(lines: list[str], top: float, avail_pt: float = 470) -> float:
    """한 줄로 보이게 — 가장 긴 줄이 상자 폭에 맞는 글자 크기(고정폭: 영문 0.5em, 한글 1em)."""
    w = max((disp_width(x.rstrip()) for x in lines), default=1)
    return max(4.6, min(top, avail_pt / (max(w, 1) * 0.5)))


def render_result(no: str, label: str, lines: list[str]) -> str:
    """'결과 | NN-NNN | 실제 …' 상자 — 명령 상자 바로 밑에 붙는 출력. 행 번호는 명령의 행 번호."""
    check = ""
    body = []
    for ln in lines:
        if ln.lstrip().startswith("✔"):
            check = ln.strip().lstrip("✔").strip()
            continue
        body.append(ln)
    size = fit_size([re.sub(r"^\s*(\d+|▷)\s{2}", "", x) for x in body], 7.2)
    rows = []
    for ln in body:
        mm = re.match(r"^\s{0,3}(\d+|▷)\s{2}(.*)$", ln)
        n, txt = (mm.group(1), mm.group(2)) if mm else ("", ln.strip())
        t = html.escape(txt)
        t = re.sub(r"(←.*)$", r'<span class="cm">\1</span>', t)
        rows.append(f'<tr{" class=\"gr\"" if n else ""}><td class="ln">{n}</td><td>{t}</td></tr>')
    kind = "plan" if label.startswith(("기대", "아직")) else "real"
    ck = (f'<div class="ck"><b>✔ 확인</b>{html.escape(check.removeprefix("확인:").strip())}</div>') if check else ""
    return (f'<div class="res {kind}"><div class="hd"><span><b>결과</b><span class="nt">{html.escape(label)}</span></span>'
            f'<span class="id">{no}</span></div><table style="font-size:{size:.2f}pt">{"".join(rows)}</table>{ck}</div>')


def figure_key(first: str, block: str):
    m = re.match(r"^그림\s*(\d+)\s*\|\s*(.*)$", first)
    if m:
        return m.group(1), f"그림 {m.group(1)}", m.group(2)
    if first.startswith("사용자 ─▶ ① "):
        return "map", "실습 지도", "사용자에서 데이터까지 — 층마다 몇 장에서 채우나"
    if first.startswith("사용자(브라우저)"):
        return "ds-arch", "그림 A", "전체 구조 — 네 상자와 상태 저장"
    if first.startswith("START →"):
        return "ds-graph", "그림 B", "에이전트 그래프의 마디와 흐름"
    if first.startswith("src/onprem_agent/"):
        return "ds-tree", "그림 C", "저장소 구조"
    return None, "", ""


# 한 줄로 보이게: 넘치는 상자는 글자를 조금씩 줄인다(실제 그린 폭으로 잰다).
FIT_JS = """() => {
  const shrink = (box, targets, min) => {
    let guard = 60;
    while (box.scrollWidth > box.clientWidth + 1 && guard--) {
      let moved = false;
      for (const t of targets) {
        const fs = parseFloat(getComputedStyle(t).fontSize);
        if (fs > min) { t.style.fontSize = (fs * 0.96) + 'px'; moved = true; }
      }
      if (!moved) break;
    }
  };
  for (const b of document.querySelectorAll('.term, .res')) {
    const t = b.querySelector('table'); if (t) shrink(b, [t], 6);
    const ck = b.querySelector('.ck'); if (ck) shrink(ck, [ck], 6);
  }
  for (const b of document.querySelectorAll('pre.out')) shrink(b, [b], 6);
  // 그림: 안쪽 상자부터 — 넘치는 상자의 글자를 줄인다
  const boxes = [...document.querySelectorAll('figure.dg .n, figure.dg .tile, figure.dg .folder, figure.dg .nest, figure.dg .grp, figure.dg .dgb')];
  boxes.sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);
  for (const b of boxes) shrink(b, [b, ...b.querySelectorAll('b, small, i, span, code, .ly')], 6.5);
  for (const t of document.querySelectorAll('table:not(.term table):not(.res table)')) {
    const p = t.parentElement; if (t.scrollWidth > p.clientWidth + 1) shrink(p, [t, ...t.querySelectorAll('td, th')], 7);
  }
}"""


def main():
    text = SRC.read_text(encoding="utf-8")
    blocks: list[str] = []

    def stash(m):
        blocks.append(m.group(1).rstrip("\n"))
        return f"\n\n@@CODE{len(blocks) - 1}@@\n\n"

    text = re.sub(r"```[a-z]*\n(.*?)```", stash, text, flags=re.S)
    text = re.sub(r"^(\d+(?:~\d+)?행)\s", r'<span class="stepno">\1</span> ', text, flags=re.M)
    body = markdown.markdown(text, extensions=["tables", "sane_lists", "pymdownx.tilde"])
    for i, b in enumerate(blocks):
        r = render_code(b)
        body = body.replace(f"<p>@@CODE{i}@@</p>", r).replace(f"@@CODE{i}@@", r)

    soup = BeautifulSoup(body, "html.parser")
    title_el = soup.find("h1")
    title = title_el.get_text() if title_el else SRC.stem
    if title_el:
        title_el.decompose()
    for hr in soup.find_all("hr"):
        hr.decompose()

    # 행별 해설
    for p in soup.find_all("p"):
        first = p.find(True)
        if first is not None and first.name == "span" and "stepno" in (first.get("class") or []) and p.contents and p.contents[0] is first:
            parts = re.split(r'\n?(?=<span class="stepno">)', p.decode_contents())
            out = ['<div class="steps">']
            for part in parts:
                mm = re.match(r'<span class="stepno">(.*?)행</span>\s*(.*)$', part.strip(), re.S)
                if mm:
                    out.append(f'<div class="st"><span class="bd">{mm.group(1)}</span><div>{mm.group(2)}</div></div>')
            out.append("</div>")
            p.replace_with(BeautifulSoup("".join(out), "html.parser"))

    # 이름 붙은 문단 → 색 상자, '실행' → 작은 머리
    for p in soup.find_all("p"):
        if not p.contents or getattr(p.contents[0], "name", None) != "strong":
            continue
        label = p.contents[0].get_text().strip()
        rest = p.decode_contents()[len(str(p.contents[0])):].lstrip()
        if label == "실행" and not rest.strip():
            p.replace_with(BeautifulSoup('<h4 class="lbl">실행</h4>', "html.parser"))
            continue
        kind = next((k for pre, k in CALLOUT if label.startswith(pre)), "note")
        rest = re.sub(r"^[·:]\s*", "", rest)
        if not BeautifulSoup(rest, "html.parser").get_text().strip():   # 머리말만 있는 문단(뒤에 표가 옴) → 작은 머리
            p.replace_with(BeautifulSoup(f'<h4 class="lbl k {kind}">{html.escape(label.rstrip(" .:"))}</h4>', "html.parser"))
            continue
        lab = label.rstrip(" .:")
        p.replace_with(BeautifulSoup(f'<div class="co {kind}"><span class="lb">{lab}</span>{rest}</div>', "html.parser"))

    # 결과 표
    for t in soup.find_all("table"):
        ths = [th.get_text() for th in t.find_all("th")]
        if ths and "결과" in ths[-1]:
            t["class"] = t.get("class", []) + ["result"]

    # 표: 칸 글이 짧은 열은 줄바꿈하지 않는다(한 줄로). 긴 열만 접힌다.
    for t in soup.find_all("table"):
        rows = [r.find_all(["td", "th"]) for r in t.find_all("tr")]
        ncol = max((len(r) for r in rows), default=0)
        for c in range(ncol):
            cells = [r[c] for r in rows if len(r) > c]
            longest = max((disp_width(x.get_text().strip()) for x in cells), default=0)
            if longest <= 34:
                for x in cells:
                    x["class"] = x.get("class", []) + ["nw"]

    # 장(h2)으로 나누고, ### 익히기 절은 상자로 묶는다
    chapters, intro = [], []
    cur = None
    for el in list(soup.contents):
        if getattr(el, "name", None) == "h2":
            cur = {"h": el.get_text(), "els": []}
            chapters.append(cur)
        elif cur is None:
            intro.append(el)
        else:
            cur["els"].append(el)

    def wrap_sections(els):
        out, box = [], None
        for el in els:
            if getattr(el, "name", None) == "h3":
                t = el.get_text()
                kind = next((k for pre, k in SECTION if t.startswith(pre)), None)
                if kind:
                    box = {"kind": kind, "title": t, "els": []}
                    out.append(box)
                    continue
                box = None
            (box["els"] if box else out).append(el)
        res = []
        for x in out:
            if isinstance(x, dict):
                inner = "".join(str(e) for e in x["els"])
                res.append(f'<section class="sx {x["kind"]}"><div class="sxh"><span class="ic2"></span>{html.escape(x["title"])}</div>{inner}</section>')
            else:
                res.append(str(x))
        return "".join(res)

    toc_rows, chap_html = [], []
    for i, ch in enumerate(chapters):
        h = ch["h"].strip()
        m = re.match(r"^(\d+)\.\s*(.*)$", h)
        no, rest = (m.group(1), m.group(2)) if m else ("", h)
        main_t, sub = (rest.split(" — ", 1) + [""])[:2]
        if not no:
            no, main_t, sub = main_t, sub or main_t, ""
        goal = ""
        for e in ch["els"]:
            if getattr(e, "name", None) == "div" and "goal" in (e.get("class") or []):
                g = e.get_text()[len("완료 목표"):].strip()
                goal = g[:96] + ("…" if len(g) > 96 else "")
                break
        word = not no.isdigit()
        toc_rows.append(f'<div class="row"><div class="no">{html.escape(no if not word else "·")}</div><div><div class="t">{html.escape(main_t if not word else (no if main_t == no else no + " — " + main_t))}</div>'
                        + (f'<div class="s">{html.escape(sub)}</div>' if sub else "")
                        + (f'<div class="g">{html.escape(goal)}</div>' if goal else "") + "</div></div>")
        head = (f'<div class="chead"><div class="no{" word" if word else ""}">{html.escape(no)}</div>'
                f'<div><div class="t">{html.escape(main_t)}</div>' + (f'<div class="s">{html.escape(sub)}</div>' if sub else "") + "</div></div>")
        chap_html.append(f'<section class="chap{" first" if i == 0 else ""}">{head}{wrap_sections(ch["els"])}</section>')

    meta = META.get(SRC.stem, dict(kicker="", lead="", meta=[], stats=[]))
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    meta_rows = "".join(f"<div><b>{html.escape(k)}</b>{html.escape(v)}</div>" for k, v in meta["meta"])
    meta_rows += f"<div><b>판</b>{date.today().isoformat()} · 커밋 {commit} · github.com/moongu0891-ship-it/onprem-agent</div>"
    stats = "".join(f'<div class="stat"><b>{html.escape(a)}</b><span>{html.escape(b)}</span></div>' for a, b in meta["stats"])
    cover = (f'<div class="cover"><div class="band"><div class="kicker">{html.escape(meta["kicker"])}</div>'
             f'<h1>{html.escape(title)}</h1><div class="lead">{html.escape(meta["lead"])}</div></div>'
             f'<div class="meta">{meta_rows}</div><div class="stats">{stats}</div></div>')
    intro_html = "".join(str(e) for e in intro if str(e).strip())
    toc = (f'<div class="toc">' + (f'<div class="intro">{intro_html}</div>' if intro_html else "")
           + f'<h2 class="tt">차례</h2>{"".join(toc_rows)}</div>')
    css = (FIG / "book.css").read_text(encoding="utf-8")
    page = (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f'<style>{css}</style></head><body>{cover}{toc}{"".join(chap_html)}</body></html>')
    tmp = DST.with_suffix(".html")
    tmp.write_text(page, encoding="utf-8")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 688, "height": 1000})   # A4 본문 폭 182mm — 이 폭에서 넘침을 잰다
        pg.goto(tmp.resolve().as_uri())
        pg.wait_for_timeout(600)
        pg.emulate_media(media="print")
        pg.evaluate(FIT_JS)
        left = pg.evaluate("""() => [...document.querySelectorAll('.term, .res, pre.out, figure.dg, figure.dg .n')]
            .filter(e => e.scrollWidth > e.clientWidth + 1).map(e => e.className + ' | ' + (e.innerText || '').slice(0, 40).replace(/\\n/g, ' '))""")
        for x in left:
            print("  넘침:", x)
        if "--html" in sys.argv:
            tmp.write_text("<!doctype html>" + pg.evaluate("document.documentElement.outerHTML"), encoding="utf-8")
        short = title.split(" — ")[0]
        pg.pdf(path=str(DST), format="A4", print_background=True, prefer_css_page_size=True,
               display_header_footer=True, header_template="<div></div>",
               footer_template='<div style="font-size:7px;color:#8a93a1;width:100%;padding:0 14mm;display:flex;justify-content:space-between;font-family:sans-serif">'
                               f'<span>{html.escape(short)}</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')
        b.close()
    if "--html" not in sys.argv:
        tmp.unlink()
    print("저장:", DST)


if __name__ == "__main__":
    main()
