// 상담 화면 — 질문을 보내면 서버가 그래프의 단계를 하나씩 보내 주고(Server-Sent Events), 화면이 그대로 그린다.
// 글은 모두 textContent 로 넣는다(답·자료 속 글을 HTML 로 해석하지 않는다).
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  };
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* 저장 못 해도 화면은 그대로 */ } },
    del(k) { try { localStorage.removeItem(k); } catch (e) { /* 위와 같음 */ } },
  };

  let desks = [];
  let desk = null;
  let thread = null;
  let busy = false;
  let turn = null;        // 지금 그리는 질문 하나: {box, sources, waiting}

  // ── 밝은 화면 / 어두운 화면 ──
  $("theme").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "light" ? "" : "light";
    if (next) document.documentElement.dataset.theme = next; else delete document.documentElement.dataset.theme;
    store.set("theme", next);
  });

  // ── 창구 ──
  async function init() {
    try {
      desks = await (await fetch("/api/desks")).json();
    } catch (e) {
      $("log").append(el("p", "error", "서버에 연결할 수 없습니다. 잠시 뒤 다시 열어 주세요."));
      return;
    }
    const box = $("desks");
    for (const d of desks) {
      const b = el("button", "tab", d.title);
      b.type = "button";
      b.dataset.desk = d.name;
      b.addEventListener("click", () => { if (!busy) pick(d.name); });
      box.append(b);
    }
    const saved = store.get("desk");
    await pick(desks.some((d) => d.name === saved) ? saved : desks[0].name);
  }

  async function pick(name) {
    desk = desks.find((d) => d.name === name);
    store.set("desk", name);
    for (const b of $("desks").children) b.setAttribute("aria-pressed", String(b.dataset.desk === name));
    $("title").textContent = desk.title;
    $("ask").placeholder = desk.placeholder;
    clearAll();
    thread = store.get("thread:" + name);
    $("thread").textContent = thread || "—";
    if (thread) await restore();
  }

  function clearAll() {
    $("log").replaceChildren($("hello") || el("p", "hello"));
    $("hello").hidden = false;
    resetSteps("질문을 보내면 AI가 처리하는 순서가 여기에 차례로 나옵니다.");
    $("degraded").hidden = true;
    turn = null;
  }

  // ── 이전 상담 이어 보기 ──
  async function restore() {
    let data;
    try {
      const r = await fetch(`/api/thread?desk=${encodeURIComponent(desk.name)}&thread=${encodeURIComponent(thread)}`);
      if (!r.ok) return;
      data = await r.json();
    } catch (e) { return; }
    if (!data.turns.length) return;
    for (const t of data.turns) {
      newTurn(t.question);
      for (const s of t.tools) addSource({ label: s.label, text: s.text, ok: s.ok, ids: [] });
      if (t.answer) addAnswer({ text: t.answer, cites: t.cites });
    }
    if (data.pending) addApproval(data.pending);
    resetSteps(data.pending ? "이전 상담을 불러왔습니다. 확인을 기다리는 일이 있습니다." : "이전 상담을 불러왔습니다.");
  }

  // ── AI가 처리한 순서 ──
  function resetSteps(text) {
    const ol = $("steps");
    ol.replaceChildren();
    if (text) ol.append(el("li", "empty", text));
  }

  function addStep(e) {
    const ol = $("steps");
    ol.querySelector(".empty")?.remove();
    if (e.label === "담당자 확인") {          // 기다리던 칸을 결과로 바꾼다
      const waiting = [...ol.querySelectorAll(".chip.wait")].pop();
      if (waiting) { paintChip(waiting, e); return; }
    }
    const li = el("li", "step");
    if (ol.children.length) {
      const arrow = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      arrow.setAttribute("width", "18"); arrow.setAttribute("height", "12"); arrow.setAttribute("viewBox", "0 0 18 12");
      arrow.setAttribute("aria-hidden", "true"); arrow.classList.add("arrow");
      const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
      p.setAttribute("d", "M1 6h14M11 2l4 4-4 4"); p.setAttribute("fill", "none"); p.setAttribute("stroke", "currentColor"); p.setAttribute("stroke-width", "1.5");
      arrow.append(p);
      li.append(arrow);
    }
    const chip = el("div", "chip");
    chip.append(el("span", "l"), el("span", "v"));
    paintChip(chip, e);
    li.append(chip);
    ol.append(li);
  }

  function paintChip(chip, e) {
    chip.className = "chip " + (e.state || "ok");
    chip.querySelector(".l").textContent = e.label;
    chip.querySelector(".v").textContent = e.value;
  }

  // ── 대화 ──
  function newTurn(question) {
    $("hello").hidden = true;
    const box = el("article", "turn");
    box.append(el("span", "label", "내 질문"), el("div", "question", question));
    $("log").append(box);
    turn = { box, sources: null, waiting: null };
  }

  function addSource(e) {
    if (!turn) return;
    if (!turn.sources) {
      const wrap = el("div", "sources");
      wrap.append(el("span", "label", "AI가 찾아본 자료"));
      turn.box.append(wrap);
      turn.sources = wrap;
    }
    const s = el("div", "src" + (e.ok === false ? " err" : ""));
    s.append(el("div", "t", e.label + (e.query ? ` · ${e.query}` : "")));
    s.append(el("div", "body", e.text));
    turn.sources.append(s);
  }

  function addApproval(e) {
    if (!turn) newTurn("(이전 질문)");
    const card = el("section", "approval");
    const h = el("h3", null, "확인해 주세요 — " + e.title);
    card.append(h, el("div", "help", "회사 시스템에 기록을 남기는 일이라, 사람이 확인한 뒤에만 실행합니다."));
    const dl = el("dl", "fields");
    for (const f of e.fields) {
      const d = el("div");
      d.append(el("dt", null, f.k), el("dd", null, f.v));
      dl.append(d);
    }
    card.append(dl);
    const actions = el("div", "actions");
    const yes = el("button", "btn primary", e.button);
    const no = el("button", "btn", "취소");
    yes.type = no.type = "button";
    yes.addEventListener("click", () => decide(true, card, e));
    no.addEventListener("click", () => decide(false, card, e));
    actions.append(yes, no);
    card.append(actions);
    turn.box.append(card);
    const w = el("div", "waiting");
    w.append(el("span", "dot"), el("span", null, "확인을 기다리고 있어요. 자리를 비웠다 와도 이 화면에서 이어집니다."));
    turn.box.append(w);
    turn.waiting = w;
    yes.focus();
  }

  async function decide(approved, card, e) {
    if (busy) return;
    card.querySelectorAll("button").forEach((b) => { b.disabled = true; });
    card.querySelector(".actions").remove();
    card.classList.add(approved ? "done" : "no");
    card.querySelector("h3").textContent = approved ? e.done : "취소하셨습니다 · 실행하지 않았습니다";
    card.querySelector(".help").remove();
    turn?.waiting?.remove();
    await stream("/api/approve", { desk: desk.name, thread, approved });
  }

  function addAnswer(e) {
    if (!turn) return;
    const a = el("section", "answer");
    a.append(el("span", "label", "AI 답변"), el("div", "text", e.text || "(답이 비어 있습니다)"));
    if (e.cites && e.cites.length) {
      const c = el("div", "cites");
      c.append(el("span", null, "출처"));
      for (const id of e.cites) c.append(el("span", "id" + (/^(TK|RQ)-/.test(id) ? " done" : ""), id));
      c.append(el("span", null, "· AI가 실제로 찾아본 자료만 표시합니다"));
      a.append(c);
    }
    turn.box.append(a);
    if (e.degraded) $("degraded").hidden = false;
    a.scrollIntoView({ block: "nearest" });
  }

  // ── 서버와 주고받기 ──
  function handle(e) {
    if (e.type === "thread") {
      thread = e.thread;
      store.set("thread:" + desk.name, thread);
      $("thread").textContent = thread;
    } else if (e.type === "step") addStep(e);
    else if (e.type === "tool") addSource(e);
    else if (e.type === "approval") addApproval(e);
    else if (e.type === "answer") addAnswer(e);
    else if (e.type === "error") turn?.box.append(el("p", "error", e.text));
  }

  async function stream(url, body) {
    busy = true;
    $("send").disabled = true;
    const note = el("div", "waiting");
    note.append(el("span", "dot busy"), el("span", null, "AI가 처리하는 중…"));
    turn?.box.append(note);
    try {
      const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!res.ok || !res.body) throw new Error(String(res.status));
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf("\n\n")) >= 0) {
          const chunk = buf.slice(0, i);
          buf = buf.slice(i + 2);
          if (chunk.startsWith("data: ")) {
            note.remove();
            handle(JSON.parse(chunk.slice(6)));
            if (turn && !turn.waiting && !turn.box.querySelector(".answer")) turn.box.append(note);
          }
        }
      }
    } catch (err) {
      turn?.box.append(el("p", "error", "서버와 연결이 끊겼습니다. 잠시 뒤 다시 보내 주세요."));
    } finally {
      note.remove();
      busy = false;
      $("send").disabled = false;
    }
  }

  $("form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const q = $("ask").value.trim();
    if (!q || busy || !desk) return;
    $("ask").value = "";
    newTurn(q);
    resetSteps();
    $("degraded").hidden = true;
    stream("/api/chat", { desk: desk.name, question: q, thread });
  });
  $("ask").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) {
      ev.preventDefault();
      $("form").requestSubmit();
    }
  });
  $("new").addEventListener("click", () => {
    if (busy) return;
    store.del("thread:" + desk.name);
    thread = null;
    $("thread").textContent = "—";
    clearAll();
    $("ask").focus();
  });

  init();
})();
