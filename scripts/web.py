"""웹 화면 띄우기 — 상담 화면 http://127.0.0.1:8080/ · 관리자 화면 http://127.0.0.1:8080/admin

    python scripts/web.py                                  # 규칙 모델(GPU 없이)
    python scripts/web.py --model sglang-4b                # 노트북: Qwen3-4B(FP8) + 생각 모드 (SGLang 을 먼저 띄운다)
    python scripts/web.py --model gateway                  # LiteLLM 게이트웨이(예비 엔진으로 넘어가면 화면에 안내)
    python scripts/web.py --embedder '{"kind":"sentence-transformers","model":"BAAI/bge-m3"}'   # 검색 임베더(노트북 기본값)

설명: src/onprem_agent/web/app.py, agent/README 7.8.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from onprem_agent.agent.defaults import MODELS  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", default="rule", choices=list(MODELS))
    ap.add_argument("--store", default="sqlite", choices=["sqlite", "memory"], help="대화·승인 대기 저장 (sqlite: var/web_state.db)")
    ap.add_argument("--host", default="127.0.0.1", help="기본은 이 컴퓨터에서만. 다른 컴퓨터에서 보려면 0.0.0.0 (인증이 없으니 사내망 안에서만)")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--embedder", default=None, help='검색 임베더 JSON (기본: 해시 임베더)')
    ap.add_argument("--results", default=None, help="관리자 화면이 읽을 결과 폴더 (기본: results/)")
    a = ap.parse_args()

    import uvicorn

    from onprem_agent.web.app import create_app
    app = create_app(a.model, a.store, Path(a.results) if a.results else None, json.loads(a.embedder) if a.embedder else None)
    print(f"상담 화면 http://{a.host}:{a.port}/  ·  관리자 화면 http://{a.host}:{a.port}/admin  ·  모델 {a.model}")
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
