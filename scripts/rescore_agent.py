"""저장된 에이전트 평가 결과(results/*.json)를 지금 채점 규칙으로 다시 채점한다 — 모델을 다시 돌리지 않는다.

    python scripts/rescore_agent.py results/agent_laptop_w5.json      # → results/agent_laptop_w5_rescored.json/.md

쓰는 경우: 채점 규칙이나 답 정리 방식을 고쳤을 때. 결과 파일의 traces 에 질문마다 업무 기능(도구) 호출·실행 결과·승인·답이
모두 남아 있으므로 그대로 다시 채점할 수 있다.
5주차: 생각 글(<think>…</think>)이 답 본문에 섞여 들어와 채점이 부풀었을 수 있어(D25), 생각 글을 뗀 답으로 다시 채점한다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from onprem_agent.agent.evaluate import score, summarize, to_markdown  # noqa: E402
from onprem_agent.agent.graph import strip_think  # noqa: E402


def main():
    src = Path(sys.argv[1])
    res = json.loads(src.read_text(encoding="utf-8"))
    tasks = {t["id"]: t for t in map(json.loads, (ROOT / "eval/agent_tasks.jsonl").read_text(encoding="utf-8").splitlines())}
    changed_total = 0
    for m in res["models"]:
        if m.get("error"):
            continue
        rows, changed = [], 0
        for tr in m["traces"]:
            answer, thoughts = strip_think(tr.get("answer") or "")
            raw, _ = strip_think(tr.get("raw_answer") or tr.get("answer") or "")
            tr2 = {**tr, "answer": answer, "raw_answer": raw}
            r = score(tasks[tr["id"]], tr2)
            old = next(x for x in m["rows"] if x["id"] == tr["id"])
            if r["success"] != old["success"]:
                changed += 1
                print(f"  [{m['label']}] {tr['id']}: {'성공' if old['success'] else '실패'} → {'성공' if r['success'] else '실패'}"
                      + (f"  — {'; '.join(r['reasons'])}" if r["reasons"] else ""))
            tr.update(answer=answer, raw_answer=raw, thinking_chars=len(thoughts))
            rows.append(r)
        before = m["summary"]["success"]
        m["rows"], m["summary"] = rows, summarize(rows)
        print(f"{m['label']}: {before:.0%} → {m['summary']['success']:.0%} (바뀐 과업 {changed})")
        changed_total += changed
    res["rescored"] = "생각 글(<think>)을 뗀 답으로 다시 채점 (scripts/rescore_agent.py)"
    out = src.with_name(src.stem + "_rescored")
    out.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    out.with_suffix(".md").write_text(to_markdown(res), encoding="utf-8")
    print(f"\n저장: {out.with_suffix('.json')}, {out.with_suffix('.md')} (바뀐 과업 합계 {changed_total})")


if __name__ == "__main__":
    main()
