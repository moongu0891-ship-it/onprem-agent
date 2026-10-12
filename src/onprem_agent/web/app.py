"""웹 화면 — 상담 화면(/)과 관리자 화면(/admin). 지금 기본값 에이전트(onprem_agent.agent.defaults)를 그대로 쓴다.

    python scripts/web.py                       # 규칙 모델(GPU 없이) · http://127.0.0.1:8080
    python scripts/web.py --model sglang-4b     # 노트북: Qwen3-4B(FP8) + 생각 모드
    python scripts/web.py --model gateway       # LiteLLM 게이트웨이(1순위 장애 시 예비 엔진, 답에 안내)

- 질문 하나를 처리하는 동안 그래프의 각 단계를 바로바로 화면에 보낸다(Server-Sent Events). 화면의 'AI가 처리한 순서'가 이것이다.
- 담당자 확인(승인)은 그래프의 승인 대기(interrupt)와 그대로 이어진다. 대화와 승인 대기는 체크포인터(SQLite)에 저장되어,
  화면을 닫았다 열어도 같은 상담 번호로 이어진다.
- 창구는 처음 쓸 때 업무 기능(도구) 서버를 띄운다(검색 색인을 만드는 데 메모리가 들어, 안 쓰는 창구는 띄우지 않는다).
- 로그인·권한은 없다(데모). 사내에 올릴 때는 앞단의 인증(8주차 워크북의 게이트웨이 장)을 거치게 한다. 기본은 이 컴퓨터(127.0.0.1)에서만 열린다.
- 화면은 밖의 글꼴·스크립트를 불러오지 않는다(사내망 전용 — 인터넷이 없어도 그대로 보인다).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from collections import deque
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from ..agent.defaults import EMPTY_ANSWER, FEATURES, GRAPH, MODELS, PROMPT_RULES, build_default_app, model_spec
from ..agent.desk import list_desks, load_desk
from ..agent.runner import ROOT, mcp_tools
from .events import TurnTracker, approval_event, split_answer, tool_label

STATIC = Path(__file__).resolve().parent / "static"
THREAD_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
GATE_LIGHT = re.compile(r"빨간불 검사:\s*(빨간불|노란불|초록불)")   # 보고서 첫 줄 "# 빨간불 검사: 초록불"


class ChatIn(BaseModel):
    desk: str
    question: str = Field(min_length=1, max_length=2000)
    thread: str | None = None


class ApproveIn(BaseModel):
    desk: str
    thread: str
    approved: bool


class DeskPool:
    """창구마다 업무 기능(도구) 서버와 에이전트를 한 번 만들어 둔다(처음 쓸 때).
    서버 연결은 창구마다 따로 도는 작업 하나가 열고 닫는다 — 연결(anyio 취소 범위)은 연 작업에서 닫아야 한다.
    요청을 처리하는 작업에서 열면 서버를 끌 때 다른 작업이 닫게 되어 오류가 났다."""

    def __init__(self, model_key: str, saver, embedder: dict):
        self.model_key, self.saver, self.embedder = model_key, saver, embedder
        self.apps: dict = {}
        self.tasks: list = []
        self.lock = asyncio.Lock()
        self.closing = asyncio.Event()

    async def _hold(self, desk: str, ready: asyncio.Future):
        try:
            async with mcp_tools(desk, {"ONPREM_EMBEDDER": json.dumps(self.embedder)}) as tools:
                ready.set_result(tools)
                await self.closing.wait()
        except Exception as e:  # 서버를 못 띄웠으면 기다리는 요청에 알린다
            if not ready.done():
                ready.set_exception(e)

    async def get(self, desk: str):
        async with self.lock:
            if desk not in self.apps:
                ready = asyncio.get_running_loop().create_future()
                self.tasks.append(asyncio.create_task(self._hold(desk, ready)))
                tools = await ready
                self.apps[desk] = build_default_app(desk, self.model_key, tools, checkpointer=self.saver)
            return self.apps[desk]

    async def close(self):
        self.closing.set()
        await asyncio.gather(*self.tasks, return_exceptions=True)


def _desk_or_404(name: str):
    if name not in list_desks():
        raise HTTPException(404, f"없는 창구: {name}")
    return load_desk(name)


def scan_results(results_dir: Path, limit: int = 12) -> list[dict]:
    """에이전트 평가 결과 파일(results/*.json, 받아들인 결과는 results/reference/)을 최근 것부터."""
    files = [*results_dir.glob("*.json"), *(results_dir / "reference").glob("*.json")] if results_dir.exists() else []
    rows = []
    for p in sorted(files, key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict) or "models" not in d or not str(d.get("config_name", "")).startswith("agent"):
            continue
        gate = p.with_name(p.stem + "_gate.md")
        light = None
        if gate.exists():
            m = GATE_LIGHT.search(gate.read_text(encoding="utf-8").split("\n", 1)[0])
            light = m.group(1) if m else None
        models = []
        for m in d["models"]:
            if m.get("error"):
                models.append({"label": m["label"], "error": m["error"][:160]})
                continue
            s, rows_ = m.get("summary", {}), m.get("rows", [])
            models.append({"label": m["label"], "n": len(rows_), "ok": sum(1 for r in rows_ if r.get("success")),
                           "unsafe": s.get("unsafe", 0), "pii": s.get("pii_leaks", 0), "false_claims": s.get("false_claims", 0)})
        rows.append({"file": p.name, "accepted": p.parent.name == "reference", "config": d.get("config_name"),
                     "at": d.get("started_at"), "gate": light, "models": models})
        if len(rows) >= limit:
            break
    return rows


async def engine_reachable(spec: dict) -> bool | None:
    if spec.get("kind") != "openai":
        return None
    import httpx
    try:
        async with httpx.AsyncClient(timeout=2.0) as c:
            r = await c.get(spec["base_url"].rstrip("/") + "/models",
                            headers={"Authorization": f"Bearer {spec.get('api_key', 'none')}"})
            return r.status_code < 500
    except httpx.HTTPError:
        return False


def create_app(model_key: str = "rule", store: str = "sqlite", results_dir: Path | None = None,
               embedder: dict | None = None) -> FastAPI:
    if model_key not in MODELS:
        raise ValueError(f"모르는 모델: {model_key} ({', '.join(MODELS)})")
    results_dir = Path(results_dir) if results_dir else ROOT / "results"
    embedder = embedder or json.loads(os.environ.get("ONPREM_EMBEDDER", '{"kind": "hash"}'))
    recent: deque = deque(maxlen=50)
    state: dict = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with AsyncExitStack() as stack:
            if store == "sqlite":
                from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
                (ROOT / "var").mkdir(exist_ok=True)
                saver = await stack.enter_async_context(AsyncSqliteSaver.from_conn_string(str(ROOT / "var/web_state.db")))
            elif store == "postgres":   # 8주차 10장: 대화·승인 대기를 공용 DB 에 — 어느 Pod 가 받아도 같은 상담을 잇는다(05장의 409 를 고침)
                from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
                dsn = os.environ.get("ONPREM_PG_DSN", "postgresql://agent:agent@localhost:5432/agent")
                saver = await stack.enter_async_context(AsyncPostgresSaver.from_conn_string(dsn))
                await saver.setup()
            else:
                from langgraph.checkpoint.memory import InMemorySaver
                saver = InMemorySaver()
            state["pool"] = DeskPool(model_key, saver, embedder)
            state["started"] = time.strftime("%Y-%m-%d %H:%M:%S")
            try:
                yield
            finally:
                await state["pool"].close()

    app = FastAPI(title="사내 AI 상담", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    async def console():
        return FileResponse(STATIC / "console.html")

    @app.get("/healthz")
    async def healthz():
        """살아 있나(liveness) — 서버 프로세스가 응답하면 200. 8주차 워크북의 Probe 가 쓴다."""
        return {"ok": True, "pod": os.environ.get("HOSTNAME", ""), "model": model_key}

    @app.get("/readyz")
    async def readyz():
        """받을 준비가 됐나(readiness) — 창구 정의를 읽을 수 있고, 실제 모델이면 엔진에 닿아야 200."""
        spec = model_spec(model_key)
        ok = bool(list_desks()) and (await engine_reachable(spec)) is not False
        if not ok:
            raise HTTPException(503, "모델 엔진에 닿지 않는다")
        return {"ready": True, "pod": os.environ.get("HOSTNAME", "")}

    @app.middleware("http")
    async def pod_header(request, call_next):
        """어느 Pod 가 답했는지(05장 로드 밸런서 관찰). HOSTNAME 은 Kubernetes 가 Pod 이름으로 채운다.
        정적 파일에는 캐시 머리말(08장 'CDN 흉내') — 브라우저·앞단 캐시가 두 번째부터 304/캐시로 답하게."""
        resp = await call_next(request)
        resp.headers["X-Served-By"] = os.environ.get("HOSTNAME", "local")
        if request.url.path.startswith("/static/"):
            resp.headers["Cache-Control"] = "public, max-age=3600"
        return resp

    @app.get("/admin")
    async def admin():
        return FileResponse(STATIC / "admin.html")

    @app.get("/api/desks")
    async def desks():
        out = []
        for name in list_desks():
            d = load_desk(name)
            out.append({"name": name, "title": d.ui.get("title") or d.title, "placeholder": d.ui.get("placeholder") or "무엇이든 물어보세요",
                        "order": d.ui.get("order", 99)})
        return sorted(out, key=lambda x: (x["order"], x["name"]))

    def log(desk: str, thread: str, question: str | None, status: str, answer: str = ""):
        for r in recent:
            if r["thread"] == thread and r["desk"] == desk and r["open"]:
                r.update(status=status, answer=answer[:160], open=status == "확인 대기", time=time.strftime("%H:%M:%S"))
                return
        recent.appendleft({"time": time.strftime("%H:%M:%S"), "desk": desk, "thread": thread, "question": (question or "")[:160],
                           "status": status, "answer": answer[:160], "open": status == "확인 대기"})

    async def run(desk_name: str, thread: str, inp, tracker: TurnTracker, first: list[dict], question: str | None):
        desk_app = await state["pool"].get(desk_name)
        cfg = {"configurable": {"thread_id": thread}}
        status, answer = "답함", ""
        yield _sse({"type": "thread", "thread": thread})
        for e in first:
            yield _sse(e)
        try:
            async for chunk in desk_app.astream(inp, cfg, stream_mode="updates"):
                for node, update in chunk.items():
                    for e in tracker.on_update(node, update):
                        if e["type"] == "approval":
                            status = "확인 대기"
                        if e["type"] == "answer":
                            answer = e["text"]
                        yield _sse(e)
        except Exception as e:  # 모델 호출 실패 등 — 화면에 알리고 끝낸다
            status = "오류"
            yield _sse({"type": "error", "text": f"처리 중 문제가 생겼습니다: {type(e).__name__}"})
        log(desk_name, thread, question, status, answer)
        yield _sse({"type": "done", "status": status})

    @app.post("/api/chat")
    async def chat(body: ChatIn):
        desk = _desk_or_404(body.desk)
        thread = body.thread or uuid.uuid4().hex[:8]
        if not THREAD_RE.match(thread):
            raise HTTPException(400, "상담 번호 형식이 아니다")
        tracker = TurnTracker(desk)
        return StreamingResponse(run(body.desk, thread, {"messages": [("user", body.question)]}, tracker,
                                     tracker.start(body.question), body.question), media_type="text/event-stream")

    @app.post("/api/approve")
    async def approve(body: ApproveIn):
        desk = _desk_or_404(body.desk)
        if not THREAD_RE.match(body.thread):
            raise HTTPException(400, "상담 번호 형식이 아니다")
        desk_app = await state["pool"].get(body.desk)
        snap = await desk_app.aget_state({"configurable": {"thread_id": body.thread}})
        if not snap.interrupts:
            raise HTTPException(409, "확인을 기다리는 일이 없다")
        tracker = TurnTracker(desk)
        tracker.decisions = 1
        resume = Command(resume={"approved": body.approved, "reason": "" if body.approved else "담당자가 취소"})
        return StreamingResponse(run(body.desk, body.thread, resume, tracker, tracker.resumed(body.approved), None),
                                 media_type="text/event-stream")

    @app.get("/api/thread")
    async def thread(desk: str, thread: str):
        d = _desk_or_404(desk)
        if not THREAD_RE.match(thread):
            raise HTTPException(400, "상담 번호 형식이 아니다")
        desk_app = await state["pool"].get(desk)
        snap = await desk_app.aget_state({"configurable": {"thread_id": thread}})
        turns = []
        for m in (snap.values or {}).get("messages", []):
            if isinstance(m, HumanMessage):
                turns.append({"question": str(m.content), "tools": [], "answer": None, "cites": []})
            elif turns and isinstance(m, ToolMessage):
                turns[-1]["tools"].append({"label": tool_label(d, m.name), "text": str(m.content)[:700], "ok": m.status == "success"})
            elif turns and isinstance(m, AIMessage) and not m.tool_calls and m.content:
                turns[-1]["answer"], turns[-1]["cites"] = split_answer(str(m.content))
        pending = None
        for intr in snap.interrupts or ():
            v = getattr(intr, "value", None) or {}
            if v.get("type") == "approval":
                pending = approval_event(d, v.get("tool_calls") or [])
        return {"thread": thread, "turns": turns, "pending": pending}

    @app.get("/api/admin")
    async def overview():
        spec = model_spec(model_key)
        on = {"nudge": GRAPH.get("require_tool") and GRAPH.get("nudge") == "search",
              "empty_answer": EMPTY_ANSWER and bool(spec.get("thinking")), "scope": "scope" in PROMPT_RULES}
        features = [{"name": n, "label": label, "what": what, "group": group, "on": bool(on.get(n, GRAPH.get(n)))}
                    for n, label, what, group in FEATURES]
        desks_out = []
        for name in list_desks():
            d = load_desk(name)
            desks_out.append({"name": name, "title": d.ui.get("title") or d.title, "open": name in state["pool"].apps, "order": d.ui.get("order", 99),
                              "tools": [tool_label(d, t) for t in (d.ui.get("tools") or {})],
                              "approval": [tool_label(d, t) for t in sorted(d.approval_tools)]})
        desks_out.sort(key=lambda x: (x["order"], x["name"]))
        return {"model": {"key": model_key, "kind": spec["kind"], "name": spec.get("model", "규칙 모델"),
                          "base_url": spec.get("base_url"), "thinking": bool(spec.get("thinking")),
                          "backup": model_key == "gateway", "reachable": await engine_reachable(spec)},
                "store": store, "started": state.get("started"), "features": features, "desks": desks_out,
                "results": scan_results(results_dir), "recent": list(recent)}

    return app


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
