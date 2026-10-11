// 관리자 화면 — /api/admin 을 읽어 그린다. 15초마다 새로 읽는다. 글은 모두 textContent 로 넣는다.
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
  };
  $("theme").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "light" ? "" : "light";
    if (next) document.documentElement.dataset.theme = next; else delete document.documentElement.dataset.theme;
    store.set("theme", next);
  });

  const row = (cells) => {
    const tr = el("tr");
    for (const c of cells) {
      const td = el("td", c && c.cls);
      if (c && c.node) td.append(c.node); else td.textContent = c && c.text !== undefined ? c.text : (c ?? "");
      tr.append(td);
    }
    return tr;
  };
  const pill = (text, kind) => el("span", "pill" + (kind ? " " + kind : ""), text);

  function drawAI(d) {
    const m = d.model;
    const dl = $("ai");
    dl.replaceChildren();
    const add = (k, v) => { dl.append(el("dt", null, k), el("dd", null, v)); };
    add("모델", m.kind === "rule" ? "규칙 모델 (GPU 없이 도는 시험용)" : m.name);
    if (m.base_url) add("연결 주소", m.base_url);
    add("생각 모드", m.thinking ? "켬" : "끔");
    add("예비 AI", m.backup ? "있음 — 주 AI가 멈추면 이어받고 답에 안내를 붙임" : "없음 (게이트웨이로 켜면 생김)");
    add("대화 저장", d.store === "sqlite" ? "켬 — 화면을 닫았다 열어도 이어짐" : "끔 — 서버를 끄면 사라짐");
    add("서버 시작", d.started || "—");
    const p = $("ai-pill");
    if (m.reachable === null) { p.textContent = "규칙 모델"; p.className = "pill"; }
    else if (m.reachable) { p.textContent = "정상"; p.className = "pill ok"; }
    else { p.textContent = "연결 안 됨"; p.className = "pill bad"; }
  }

  function drawFeatures(d) {
    const box = $("feats");
    box.replaceChildren();
    for (const group of ["안전 기능", "보호 기능(가드레일)"]) {
      box.append(el("div", "note", group === "안전 기능" ? "정확하게 — 안전 기능" : "안전하게 — 보호 기능(가드레일)"));
      const ul = el("ul", "feats");
      for (const f of d.features.filter((x) => x.group === group)) {
        const li = el("li");
        li.append(pill(f.on ? "켬" : "끔", f.on ? "ok" : ""));
        const t = el("div");
        t.append(el("div", null, f.label), el("div", "what", f.what));
        li.append(t);
        ul.append(li);
      }
      box.append(ul);
    }
  }

  function drawDesks(d) {
    const tb = $("desks");
    tb.replaceChildren();
    for (const k of d.desks) {
      tb.append(row([{ text: k.title, cls: "nowrap" }, { text: k.tools.join(" · ") }, { text: k.approval.length ? k.approval.join(" · ") : "없음" },
        { node: pill(k.open ? "사용 중" : "아직 안 씀", k.open ? "ok" : "") }]));
    }
  }

  function drawResults(d) {
    const tb = $("results");
    tb.replaceChildren();
    if (!d.results.length) {
      tb.append(row([{ text: "결과 파일이 없습니다. 노트북에서 make test-full 을 돌리면 여기에 나옵니다." }, "", "", "", "", "", ""]));
      return;
    }
    for (const r of d.results) {
      const head = el("div");
      head.append(el("div", "mono", r.file));
      const tags = el("div");
      if (r.accepted) tags.append(pill("받아들인 결과", "ok"), document.createTextNode(" "));
      if (r.gate) tags.append(pill(r.gate, r.gate === "빨간불" ? "bad" : r.gate === "노란불" ? "warn" : "ok"));
      head.append(tags);
      r.models.forEach((m, i) => {
        const first = i === 0;
        if (m.error) {
          tb.append(row([first ? { node: head } : "", first ? { text: (r.at || "").replace("T", " ").slice(0, 16) } : "", { text: m.label },
            { node: pill("실행 오류", "bad") }, "", "", ""]));
          return;
        }
        const zero = (v) => ({ node: pill(String(v), v ? "bad" : "ok"), cls: "num" });
        tb.append(row([first ? { node: head } : "", first ? { text: (r.at || "").replace("T", " ").slice(0, 16) } : "", { text: m.label },
          { text: `${m.ok}/${m.n} (${m.n ? Math.round((100 * m.ok) / m.n) : 0}%)`, cls: "num" }, zero(m.unsafe), zero(m.pii), zero(m.false_claims)]));
      });
    }
  }

  function drawRecent(d) {
    const tb = $("recent");
    tb.replaceChildren();
    if (!d.recent.length) { tb.append(row([{ text: "아직 상담이 없습니다." }, "", "", "", ""])); return; }
    const title = Object.fromEntries(d.desks.map((k) => [k.name, k.title]));
    for (const r of d.recent) {
      const kind = r.status === "확인 대기" ? "warn" : r.status === "오류" ? "bad" : "ok";
      tb.append(row([{ text: r.time, cls: "num" }, { text: title[r.desk] || r.desk, cls: "nowrap" }, { text: r.question }, { node: pill(r.status, kind) }, { text: r.answer }]));
    }
  }

  async function load() {
    try {
      const d = await (await fetch("/api/admin")).json();
      drawAI(d); drawFeatures(d); drawDesks(d); drawResults(d); drawRecent(d);
      $("updated").textContent = "갱신 " + new Date().toLocaleTimeString("ko-KR");
    } catch (e) {
      $("updated").textContent = "서버에 연결할 수 없습니다";
    }
  }
  $("refresh").addEventListener("click", load);
  load();
  setInterval(load, 15000);
})();
