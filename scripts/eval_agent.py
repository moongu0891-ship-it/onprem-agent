"""에이전트 과업 평가: 같은 과업 23개를 모델마다 끝까지 돌려 채점한다.

    python scripts/eval_agent.py configs/agent_ci.yaml                 # 규칙 모델만 (GPU 없이, CI)
    python scripts/eval_agent.py configs/agent_laptop.yaml --manage    # 엔진을 하나씩 띄우고 재고 내린다

결과: results/<이름>.json · .md (확정본은 사람이 골라 reports/ 로)
과업마다 새 대화(thread)로 시작하고, 승인 요청이 오면 과업이 정한 대로 승인·거절한다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from onprem_agent.agent.evaluate import score, summarize, to_markdown  # noqa: E402
from onprem_agent.agent.graph import build_graph  # noqa: E402
from onprem_agent.agent.prompts import SYSTEM  # noqa: E402
from onprem_agent.agent.runner import make_model, mcp_tools, run_task  # noqa: E402


async def eval_model(spec, tasks, mcp_env, only_ids=None, graph_opts=None):
    graph_opts = graph_opts or {}
    from langgraph.checkpoint.memory import InMemorySaver
    rows, traces = [], []
    for scenario in ("ops", "cs"):
        ts = [t for t in tasks if t["scenario"] == scenario and (not only_ids or t["id"] in only_ids)]
        if not ts:
            continue
        async with mcp_tools(scenario, mcp_env) as tools:
            app = build_graph(make_model(spec, scenario), tools, SYSTEM[scenario], checkpointer=InMemorySaver(),
                              max_steps=spec.get("max_steps", 6), **graph_opts)
            for t in ts:
                tr = await run_task(app, t["question"], approval=t["approval"] or "approve")
                r = score(t, tr)
                rows.append(r)
                traces.append({"id": t["id"], **tr})
                mark = "성공" if r["success"] else "실패"
                print(f"  [{spec['label']}] {t['id']:<7} {mark}  {tr['seconds']:5.1f}s  호출 {len(tr['tool_calls'])}"
                      + (f"  — {'; '.join(r['reasons'])}" if r["reasons"] else ""))
    return rows, traces


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--only", nargs="*", help="이 문자열이 이름에 들어간 모델만")
    ap.add_argument("--tasks", nargs="*", help="이 과업 id 만")
    ap.add_argument("--manage", action="store_true", help="모델마다 docker compose 로 엔진을 띄우고 내린다")
    ap.add_argument("--ready-timeout", type=int, default=1200)
    a = ap.parse_args()
    cfg = yaml.safe_load(Path(a.config).read_text(encoding="utf-8"))
    tasks = [json.loads(x) for x in (ROOT / cfg.get("tasks", "eval/agent_tasks.jsonl")).read_text(encoding="utf-8").splitlines() if x.strip()]
    mcp_env = {"ONPREM_EMBEDDER": json.dumps(cfg.get("embedder", {"kind": "hash"}))}

    res = {"config_name": cfg["name"], "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "n_tasks": len(tasks), "n_ops": sum(t["scenario"] == "ops" for t in tasks),
           "n_cs": sum(t["scenario"] == "cs" for t in tasks), "embedder": cfg.get("embedder"), "models": []}
    for spec in cfg["models"]:
        if a.only and not any(o in spec["label"] for o in a.only):
            continue
        print(f"\n== {spec['label']}")
        profile = spec.get("profile")
        try:
            if a.manage and profile:
                from bench_serving import compose, wait_ready
                compose(profile, "up")
                wait_ready(spec["base_url"], spec.get("headers", {}), a.ready_timeout, profile)
            graph_opts = {**cfg.get("graph", {}), **spec.get("graph", {})}   # 설정 파일 기본값 위에 모델별 값
            rows, traces = asyncio.run(eval_model(spec, tasks, mcp_env, a.tasks, graph_opts))
            res["models"].append({"label": spec["label"], "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                  "graph": graph_opts,
                                  "spec": {k: v for k, v in spec.items() if k != "headers"},
                                  "summary": summarize(rows), "rows": rows, "traces": traces})
            s = res["models"][-1]["summary"]
            print(f"  → 과업 성공 {s['success']:.0%}  도구 {s['tools_ok']:.0%}  승인 {s['approval_ok']:.0%}  답 {s['answer_ok']:.0%}  "
                  f"위험 행동 {s['unsafe']}  개인정보 노출 {s['pii_leaks']}  거짓 실행 보고 {s['false_claims']}  "
                  f"되돌림 {s['nudged']}  시간 p50 {s['seconds_p50']:.1f}s")
        except Exception as e:
            msg = f"{type(e).__name__}: {str(e)[:300]}"
            if a.manage and profile:
                from bench_serving import save_logs
                msg += f" — 엔진 로그: {save_logs(profile, cfg['name'] + '_' + spec['label'].replace(' ', '_'))}"
            print(f"  건너뜀: {msg}")
            res["models"].append({"label": spec["label"], "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "error": msg})
        finally:
            if a.manage and profile:
                from bench_serving import compose
                compose(profile, "down")

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    name = cfg["name"] + ("_partial" if a.tasks else "")   # 일부 과업만 돌린 결과는 전체 결과와 섞지 않는다
    prev_path = out / f"{name}.json"
    if a.only and prev_path.exists():
        # --only 로 일부 모델만 다시 돌렸으면, 이전에 잰 다른 모델 결과는 지우지 않고 남긴다(설정 파일 순서 유지)
        prev = {m["label"]: m for m in json.loads(prev_path.read_text(encoding="utf-8")).get("models", [])}
        new = {m["label"]: m for m in res["models"]}
        res["models"] = [new.get(s["label"]) or prev[s["label"]] for s in cfg["models"] if s["label"] in new or s["label"] in prev]
    (out / f"{name}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / f"{name}.md").write_text(to_markdown(res), encoding="utf-8")
    print(f"\n저장: results/{name}.json, results/{name}.md")
    gate = cfg.get("min_success")
    if gate is not None:
        worst = min((m["summary"]["success"] for m in res["models"] if not m.get("error")), default=0)
        if worst < gate:
            sys.exit(f"회귀 검사 실패: 과업 성공 {worst:.0%} < {gate:.0%}")
        print(f"회귀 검사 통과: 과업 성공 ≥ {gate:.0%}")


if __name__ == "__main__":
    main()
