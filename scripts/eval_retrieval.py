"""검색 평가 실행기.

    python scripts/eval_retrieval.py configs/retrieval_baseline.yaml
    python scripts/eval_retrieval.py configs/retrieval_bge.yaml --min-recall3 0.8   # 회귀 검사

결과: results/<설정이름>.json, reports/<설정이름>.md
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--min-recall3", type=float, default=None)
    args = ap.parse_args()

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    print(f"설정: {config.get('name')}")
    results = run_suite(config, ROOT)

    name = config.get("name", Path(args.config).stem)
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "results" / f"{name}.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "reports" / f"{name}.md").write_text(to_markdown(results), encoding="utf-8")
    print(f"저장: results/{name}.json, reports/{name}.md")

    if args.min_recall3 is not None:
        gate = config.get("gate_label")
        failed = []
        for sc_name, sc in results["scenarios"].items():
            for r in sc["results"]:
                if r["label"] == gate and r["overall"]["recall@3"] < args.min_recall3:
                    failed.append(f"{sc_name}: {gate} R@3 {r['overall']['recall@3']:.2f} < {args.min_recall3}")
        if failed:
            print("회귀 검사 실패:\n  " + "\n  ".join(failed))
            sys.exit(1)
        print(f"회귀 검사 통과: {gate} R@3 >= {args.min_recall3}")


if __name__ == "__main__":
    main()
