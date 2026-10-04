"""서빙 측정 결과(JSON) → Markdown 표."""

from __future__ import annotations

WL_NAMES = {"chat": "chat (짧은 질문, 앞부분 공유 거의 없음)",
            "rag": "rag (긴 에이전트 시스템 프롬프트 + 문서 3개 + 질문)",
            "multiturn": "multiturn (rag 로 시작해 같은 대화에서 3턴)"}


def _f(x, fmt="{:.0f}"):
    return "—" if x is None else fmt.format(x)


def to_markdown(res: dict) -> str:
    slo = res["slo"]
    lines = [f"# 서빙 측정: {res['config_name']}", "",
             f"- 실행: {res['started_at']} · 모델: {res['model_note']}",
             f"- 출력 {res['max_tokens']}토큰 고정 · 단계당 요청 {res['requests_per_level']}개 · 동시 사용자 {res['levels']}",
             f"- 목표(SLO): 첫 토큰 ≤ {slo['ttft_ms']} ms, 토큰당 ≤ {slo['tpot_ms']} ms. "
             "굿풋 = 목표를 지킨 요청만 센 초당 처리량", ""]
    engines = res["engines"]
    for e in engines:
        if e.get("error"):
            lines.append(f"- **{e['label']}**: 실행 안 됨 — {e['error'][:200]}")
    lines.append("")

    wls = []
    for e in engines:
        for w in e.get("workloads", {}):
            if w not in wls:
                wls.append(w)
    for w in wls:
        lines += [f"## {WL_NAMES.get(w, w)}", "",
                  "| 엔진 | 동시 | 요청/s | 출력 토큰/s | TTFT p50 | TTFT p95 | TPOT p50 | TPOT p95 | 목표 달성 | 굿풋 요청/s | 캐시 재사용 | 오류 |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for e in engines:
            for lv in e.get("workloads", {}).get(w, []):
                s = lv["summary"]
                lines.append(
                    f"| {e['label']} | {lv['concurrency']} | {s['req_per_s']:.2f} | {s['out_tok_per_s']:.0f} "
                    f"| {_f(s['ttft_ms']['p50'])} | {_f(s['ttft_ms']['p95'])} | {_f(s['tpot_ms']['p50'], '{:.1f}')} "
                    f"| {_f(s['tpot_ms']['p95'], '{:.1f}')} | {s['slo_attainment']:.0%} | {s['goodput_req_per_s']:.2f} "
                    f"| {_f(s['cache_hit_ratio'], '{:.0%}')} | {s['errors']} |")
        lines.append("")
        for e in engines:
            for lv in e.get("workloads", {}).get(w, []):
                if lv["summary"]["errors"]:
                    lines.append(f"- {e['label']} 동시 {lv['concurrency']} 오류 예: {lv['summary']['error_samples'][:1]}")
        # 엔진별 최대 굿풋
        best = []
        for e in engines:
            lvls = e.get("workloads", {}).get(w, [])
            if lvls:
                b = max(lvls, key=lambda x: x["summary"]["goodput_req_per_s"])
                best.append(f"{e['label']} {b['summary']['goodput_req_per_s']:.2f} (동시 {b['concurrency']})")
        if best:
            lines += ["최대 굿풋: " + " · ".join(best), ""]
        lines.append(f"(입력 토큰 평균: " + ", ".join(
            f"{e['label']} {e['workloads'][w][0]['summary']['mean_prompt_tokens']:.0f}"
            for e in engines if e.get("workloads", {}).get(w)) + ")")
        lines.append("")

    tc = [e for e in engines if e.get("toolcheck")]
    if tc:
        lines += ["## 도구 호출 검사", "",
                  "| 엔진 | 문항 | 도구 선택 정확도 | 인자까지 정확 | JSON 형식 오류 | 요청 오류 | 지연 p50(ms) |",
                  "|---|---|---|---|---|---|---|"]
        for e in tc:
            t = e["toolcheck"]
            lines.append(f"| {e['label']} | {t['n']} | {t['tool_accuracy']:.2f} | {t['args_accuracy']:.2f} "
                         f"| {t['parse_errors']} | {t['request_errors']} | {_f(t['latency_ms_p50'])} |")
        lines.append("")
        for e in tc:
            if e["toolcheck"]["misses"]:
                lines.append(f"<details><summary>{e['label']} — 틀린 문항 {len(e['toolcheck']['misses'])}개</summary>\n")
                for m in e["toolcheck"]["misses"]:
                    lines.append(f"- `{m['id']}` 기대 {m['want']} → 받음 {m.get('got')} {m.get('args', '')} {m.get('error', '')}")
                lines.append("\n</details>\n")
    return "\n".join(lines)
