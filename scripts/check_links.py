"""문서 링크·앵커 검사 — 저장소의 모든 .md 에서 상대 링크의 파일과 #앵커가 있는지 본다 (make check-docs, CI).

    python scripts/check_links.py          # 문제가 있으면 목록을 찍고 종료 코드 1

앵커는 GitHub 규칙을 흉내 낸다: 소문자로, 글자·숫자·_·-·공백만 남기고, 공백은 - 로. 같은 제목이 또 나오면 -1, -2.
주의: ①·② 같은 동그라미 숫자는 GitHub 과 다르게 처리될 수 있어 제목에 쓰지 않는다(문제해결 이력 참고).
"""
import re
import sys
from pathlib import Path
root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
def slug(h):
    h = h.strip().lower()
    h = re.sub(r"[^\w\- ]", "", h, flags=re.U)   # 문자·숫자·_·-·공백만
    return h.replace(" ", "-")
anchors = {}
SKIP = {".git", "results", "results.bak", "node_modules", ".venv", ".pytest_cache", ".ruff_cache"}
files = [p for p in root.rglob("*.md") if not SKIP & set(p.relative_to(root).parts)]
for p in files:
    seen, out = {}, set()
    incode = False
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"): incode = not incode; continue
        if incode: continue
        m = re.match(r"#{1,6}\s+(.*)", line)
        if m:
            s = slug(re.sub(r"`|\*\*|\[([^\]]*)\]\([^)]*\)", lambda x: x.group(1) or "", m.group(1)))
            n = seen.get(s, 0); seen[s] = n + 1
            out.add(s if n == 0 else f"{s}-{n}")
    anchors[p.resolve()] = out
bad = 0
for p in files:
    text = p.read_text(encoding="utf-8")
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    for m in re.finditer(r"\]\(([^)\s]+)\)", text):
        link = m.group(1)
        if re.match(r"https?:|mailto:", link): continue
        path, _, frag = link.partition("#")
        tgt = (p.parent / path).resolve() if path else p.resolve()
        if not tgt.exists():
            print(f"없는 파일: {p.relative_to(root)} → {link}"); bad += 1; continue
        if frag and tgt.suffix == ".md" and frag not in anchors.get(tgt, set()):
            print(f"없는 앵커: {p.relative_to(root)} → {link}"); bad += 1
print(f"문서 {len(files)}개, 링크 문제 {bad}건")
sys.exit(1 if bad else 0)
