"""평가 하네스: 같은 문서·같은 질문으로 여러 검색 갈래를 재고 표로 남긴다.

설계 원칙
- 한 번의 실행에서 바뀌는 건 '검색 갈래'뿐이다. 문서, 청킹, 질문, k 는 모두 고정.
- 점수는 질문 유형(code / paraphrase)별로 나눠 낸다. 전체 평균 하나로 뭉뚱그리면
  "코드는 잘 찾는데 바꿔 말하면 못 찾는다" 가 숨는다.
- 색인 시간과 질의 지연(p50/p95)도 함께 잰다. 벡터DB 비교의 절반은 속도·비용이다.
"""

from __future__ import annotations

import json
import platform
import statistics
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from ..corpus import Chunk, load_corpus
from ..retrieval import build_retriever
from .metrics import mrr, percentile, recall_at_k

KS = (1, 3, 5)


def load_questions(path) -> list[dict]:
    paths = path if isinstance(path, list) else [path]
    return [json.loads(line) for p in paths
            for line in Path(p).read_text(encoding="utf-8").splitlines() if line.strip()]


def evaluate_retriever(retriever, chunks: list[Chunk], questions: list[dict], fetch: int = 20) -> dict:
    t0 = time.perf_counter()
    retriever.index(chunks)
    index_s = time.perf_counter() - t0

    per_q, lat = [], []
    for q in questions:
        t = time.perf_counter()
        hits = retriever.search(q["question"], fetch)
        lat.append((time.perf_counter() - t) * 1000)
        ranked = [h.section_id for h in hits]
        row = {"id": q["id"], "type": q["type"], "mrr": mrr(ranked, q["gold"]),
               "top3": list(dict.fromkeys(ranked))[:3], "gold": q["gold"]}
        for k in KS:
            row[f"r@{k}"] = recall_at_k(ranked, q["gold"], k)
        per_q.append(row)

    def summarize(rows):
        out = {f"recall@{k}": statistics.mean(r[f"r@{k}"] for r in rows) for k in KS}
        out["mrr"] = statistics.mean(r["mrr"] for r in rows)
        out["n"] = len(rows)
        return out

    by_type = defaultdict(list)
    for r in per_q:
        by_type[r["type"]].append(r)
    return {
        "retriever": retriever.name,
        "overall": summarize(per_q),
        "by_type": {t: summarize(rs) for t, rs in sorted(by_type.items())},
        "index_seconds": index_s,
        "latency_ms": {"p50": percentile(lat, 50), "p95": percentile(lat, 95)},
        "misses": [r for r in per_q if r["r@3"] < 1.0],
        "timings": dict(getattr(retriever, "timings", {})),
        "intent_errors": _intent_errors(retriever, questions),
        "rerank_ms": ({"p50": percentile(retriever.rerank_ms, 50), "p95": percentile(retriever.rerank_ms, 95)}
                      if getattr(retriever, "rerank_ms", None) else None),
        "ann_recall@10": (statistics.mean(retriever.ann_recalls) if getattr(retriever, "ann_recalls", None) else None),
        "store_latency_ms": ({"p50": percentile(retriever.store_latencies_ms, 50),
                              "p95": percentile(retriever.store_latencies_ms, 95)}
                             if getattr(retriever, "store_latencies_ms", None) else None),
    }


def _intent_errors(retriever, questions) -> list[dict] | None:
    """의도 분류가 틀린 질문 (정답 절의 종류와 고른 필터가 다름). 의도 필터를 쓰는 갈래에서만."""
    decisions = getattr(retriever, "decisions", None)
    if decisions is None:
        inner = getattr(retriever, "inner", None)
        decisions = getattr(inner, "decisions", None)
    if not decisions:
        return None
    wrong = []
    for q, (_, chosen) in zip(questions, decisions):
        want = "work_order" if q["gold"][0].startswith("WO-") else "manual"
        if chosen != want:
            wrong.append({"id": q["id"], "chose": chosen, "want": want})
    return wrong


def run_suite(config: dict, root: Path, only: list[str] | None = None) -> dict:
    """config 형식은 configs/*.yaml 참고."""
    chunking = config.get("chunking", {"max_chars": 600, "overlap": 80})
    results = {"config_name": config.get("name", "unnamed"),
               "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "env": {"python": platform.python_version(), "machine": platform.machine(), "node": platform.node()},
               "chunking": chunking, "scenarios": {}}
    for sc in config["scenarios"]:
        docs = sc["docs"] if isinstance(sc["docs"], list) else [sc["docs"]]
        chunks = [c for d in docs for c in load_corpus(root / d, **chunking)]
        qs = sc["questions"] if isinstance(sc["questions"], list) else [sc["questions"]]
        questions = load_questions([root / q for q in qs])
        rows = []
        for spec in config["retrievers"]:
            label = spec.get("label", spec["kind"])
            if only and not any(o in label for o in only):
                continue
            try:
                retriever = build_retriever(spec, config.get("defaults"))
                res = evaluate_retriever(retriever, chunks, questions)
            except Exception as e:  # DB 가 안 떠 있어도 나머지 비교는 계속한다
                print(f"  [{sc['name']}] {label:<28} 건너뜀: {type(e).__name__}: {str(e)[:120]}")
                rows.append({"label": label, "error": f"{type(e).__name__}: {str(e)[:300]}"})
                continue
            res["label"] = label
            rows.append(res)
            o = res["overall"]
            print(f"  [{sc['name']}] {res['label']:<28} R@1 {o['recall@1']:.2f}  R@3 {o['recall@3']:.2f}  "
                  f"MRR {o['mrr']:.2f}  p50 {res['latency_ms']['p50']:.1f}ms")
        results["scenarios"][sc["name"]] = {"n_chunks": len(chunks), "n_questions": len(questions), "results": rows}
    return results


def to_markdown(results: dict) -> str:
    lines = [f"# 검색 평가: {results['config_name']}", "",
             f"- 실행: {results['started_at']} · Python {results['env']['python']} · {results['env']['machine']}",
             f"- 청킹: 최대 {results['chunking']['max_chars']}자, 겹침 {results['chunking']['overlap']}자", ""]
    for name, sc in results["scenarios"].items():
        lines += [f"## 시나리오: {name} (청크 {sc['n_chunks']}개, 질문 {sc['n_questions']}개)", "",
                  "| 갈래 | R@1 | R@3 | R@5 | MRR | 코드 R@3 | 바꿔 말하기 R@3 | 어려운 R@3 | 이력 R@3 | 색인(s) | p50(ms) | p95(ms) |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in sc["results"]:
            if "error" in r:
                lines.append(f"| {r['label']} | 실행 안 됨: {r['error'][:60]} |||||||||| ")
                continue
            o, bt = r["overall"], r["by_type"]
            by = [bt.get(t, {}).get("recall@3", float("nan")) for t in ("code", "paraphrase", "hard", "history")]
            lines.append(f"| {r['label']} | {o['recall@1']:.2f} | {o['recall@3']:.2f} | {o['recall@5']:.2f} | {o['mrr']:.2f} "
                         f"| {by[0]:.2f} | {by[1]:.2f} | {by[2]:.2f} | {by[3]:.2f} | {r['index_seconds']:.2f} "
                         f"| {r['latency_ms']['p50']:.1f} | {r['latency_ms']['p95']:.1f} |")
        lines.append("")
        stores = [r for r in sc["results"] if "error" not in r and r.get("store_latency_ms")]
        if stores:
            lines += ["저장소 비교 (모든 저장소가 같은 벡터·같은 HNSW 설정을 씀. 근사 재현율 = 전수 비교 상위 10개를 되찾은 비율, 1.00 이 정확)", "",
                      "| 갈래 | 근사 재현율@10 | 임베딩(s) | 저장소 적재(s) | DB 검색 p50(ms) | DB 검색 p95(ms) |", "|---|---|---|---|---|---|"]
            for r in stores:
                t, sl = r["timings"], r["store_latency_ms"]
                ar = r.get("ann_recall@10")
                lines.append(f"| {r['label']} | {ar:.2f} | {t.get('embed_s', 0):.2f} | {t.get('store_add_s', 0):.2f} "
                             f"| {sl['p50']:.2f} | {sl['p95']:.2f} |")
            lines.append("")
        extras = [r for r in sc["results"] if "error" not in r and (r.get("intent_errors") is not None or r.get("rerank_ms"))]
        for r in extras:
            if r.get("intent_errors") is not None:
                errs = r["intent_errors"]
                lines.append(f"- {r['label']}: 의도 오분류 {len(errs)}건" + (f" {[e['id'] for e in errs]}" if errs else ""))
            if r.get("rerank_ms"):
                lines.append(f"- {r['label']}: 리랭크 지연 p50 {r['rerank_ms']['p50']:.0f} ms, p95 {r['rerank_ms']['p95']:.0f} ms")
        if extras:
            lines.append("")
        for r in sc["results"]:
            if r.get("misses"):
                lines.append(f"<details><summary>{r['label']} — 상위 3개에서 놓친 질문 {len(r['misses'])}개</summary>\n")
                for m in r["misses"]:
                    lines.append(f"- `{m['id']}` 정답 {m['gold']} → 상위 3: {m['top3']}")
                lines.append("\n</details>\n")
    return "\n".join(lines)
