"""창구(desk) 정의 읽기 — 핵심 코드가 창구를 아는 유일한 길 (7주차 ①).

창구 하나 = 시스템 지시문 + 업무 기능(도구) 서버 + 검색 업무 기능(도구) 이름 + 승인이 필요한 업무 기능(도구) + 안전 질문 낱말
+ 답 검사 머리말·거절 문구 + no_tool_needed 설명 + 창구별 지시문 규칙 + 규칙 모델. 모두 `<창구 폴더>/desk.yaml` 에 적는다(예: examples/desks/ops/desk.yaml).
핵심(그래프·안전 기능·보호 기능(가드레일)·평가기·실행기)은 이 파일만 읽으므로, 새 창구는 폴더 하나를 더해 붙인다.

창구 폴더를 찾는 곳: 환경 변수 ONPREM_DESKS(여러 개면 OS 경로 구분자로) → 없으면 저장소의 examples/desks.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def desk_dirs() -> list[Path]:
    env = os.environ.get("ONPREM_DESKS")
    return [Path(p) for p in env.split(os.pathsep) if p] if env else [ROOT / "examples/desks"]


@dataclass(frozen=True)
class Desk:
    name: str
    title: str
    root: Path                      # 창구 폴더
    prompt: str                     # 이 창구 몫의 시스템 지시문(공통 규칙은 핵심이 붙인다)
    server: Path                    # 업무 기능(도구) 서버 파일
    rules: Path | None              # 규칙 모델 파일
    search_tool: str | None = None
    approval_tools: frozenset = frozenset()
    safety_pattern: str | None = None
    prompt_markers: tuple = ()
    prompt_refusal: str | None = None
    no_tool_description: str | None = None
    claim_pattern: str | None = None    # 채점기: '실행했다'고 말하는 표현(거짓 실행 보고). 없으면 핵심의 기본(티켓·작업 요청·접수)
    prompt_rules: dict = field(default_factory=dict)

    def graph_kwargs(self) -> dict:
        """그래프에 넘길 창구별 값."""
        return {"search_tool": self.search_tool, "approval_tools": self.approval_tools,
                "safety_pattern": re.compile(self.safety_pattern) if self.safety_pattern else None,
                "prompt_markers": self.prompt_markers, "prompt_refusal": self.prompt_refusal,
                "no_tool_description": self.no_tool_description}


@lru_cache(maxsize=None)
def load_desk(name: str) -> Desk:
    import yaml
    for d in desk_dirs():
        f = d / name / "desk.yaml"
        if f.exists():
            spec = yaml.safe_load(f.read_text(encoding="utf-8"))
            root = f.parent
            return Desk(name=spec["name"], title=spec.get("title", spec["name"]), root=root,
                        prompt=(root / spec["prompt"]).read_text(encoding="utf-8").rstrip("\n"),
                        server=root / spec["server"], rules=(root / spec["rules"]) if spec.get("rules") else None,
                        search_tool=spec.get("search_tool"), approval_tools=frozenset(spec.get("approval_tools") or []),
                        safety_pattern=spec.get("safety_pattern"), prompt_markers=tuple(spec.get("prompt_markers") or []),
                        prompt_refusal=spec.get("prompt_refusal"), no_tool_description=spec.get("no_tool_description"),
                        claim_pattern=spec.get("claim_pattern"),
                        prompt_rules=dict(spec.get("prompt_rules") or {}))
    raise FileNotFoundError(f"창구 '{name}' 의 desk.yaml 이 없다: {[str(d) for d in desk_dirs()]}")


def list_desks() -> list[str]:
    return sorted({p.parent.name for d in desk_dirs() if d.exists() for p in d.glob("*/desk.yaml")})
