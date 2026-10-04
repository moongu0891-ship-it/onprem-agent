"""검색 평가 실행기.

    python scripts/eval_retrieval.py configs/retrieval_baseline.yaml
    python scripts/eval_retrieval.py configs/retrieval_bge.yaml --min-recall3 0.8   # 회귀 검사

결과: results/<설정이름>.json, results/<설정이름>.md  (results/ 는 Git 이 추적하지 않는다)
확정본은 reports/ 에 사람이 골라 옮긴다 — 측정하는 쪽과 커밋하는 쪽이 같은 파일을 건드려 충돌하지 않게.
--repeat N: 같은 설정을 N 번 재서 R@3·근사 재현율의 최소~최대를 함께 보고한다 (HNSW 는 만들 때마다 조금씩 다르다).
--min-recall3 를 주면 어느 시나리오든 '기준 갈래'(설정의 gate_label)의 Recall@3 이 그보다 낮을 때 실패(종료 코드 1).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from onprem_agent.eval.harness import run_suite, to_markdown  # noqa: E402


def repeat_table(runs: list[dict]) -> str:
    """회차별로 달라지는 폭: 최소~최대."""
    lines = [f"## 반복 측정 {len(runs)}회 — 최소~최대", "",
             "| 시나리오 | 갈래 | R@3 | 근사 재현율@10 |", "|---|---|---|---|"]
    for sc_name, sc in runs[0]["scenarios"].items():
        for j, r0 in enumerate(sc["results"]):
            if "error" in r0:
                continue
            rs = [run["scenarios"][sc_name]["results"][j] for run in runs]
            r3 = [r["overall"]["recall@3"] for r in rs if "overall" in r]
            ar = [r["ann_recall@10"] for r in rs if r.get("ann_recall@10") is not None]
            ann = f"{min(ar):.2f}~{max(ar):.2f}" if ar else "-"
            lines.append(f"| {sc_name} | {r0['label']} | {min(r3):.2f}~{max(r3):.2f} | {ann} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--min-recall3", type=float, default=None)
    ap.add_argument("--only", nargs="*", help="라벨에 이 글자가 들어간 갈래만 실행 (예: --only bm25 qdrant)")
    ap.add_argument("--repeat", type=int, default=1, help="반복 측정 횟수 (실행마다 달라지는 폭을 보려면 3 이상)")
    args = ap.parse_args()

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    print(f"설정: {config.get('name')}")
    runs = []
    for i in range(args.repeat):
        if args.repeat > 1:
            print(f"--- {i + 1}/{args.repeat} 회차 ---")
        runs.append(run_suite(config, ROOT, only=args.only))
    results = runs[-1]

    name = config.get("name", Path(args.config).stem)
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    md = to_markdown(results)
    if args.repeat > 1:
        md += "\n" + repeat_table(runs)
    (out / f"{name}.json").write_text(json.dumps(runs if args.repeat > 1 else results, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    (out / f"{name}.md").write_text(md, encoding="utf-8")
    print(f"저장: results/{name}.json, results/{name}.md")

    if args.min_recall3 is not None:
        gate = config.get("gate_label")
        failed = []
        for sc_name, sc in results["scenarios"].items():
            for r in sc["results"]:
                if r["label"] == gate and "error" not in r and r["overall"]["recall@3"] < args.min_recall3:
                    failed.append(f"{sc_name}: {gate} R@3 {r['overall']['recall@3']:.2f} < {args.min_recall3}")
        if failed:
            print("회귀 검사 실패:\n  " + "\n  ".join(failed))
            sys.exit(1)
        print(f"회귀 검사 통과: {gate} R@3 >= {args.min_recall3}")


if __name__ == "__main__":
    main()
