// Ledger to Regulator. Every number comes from data.json, exported from the tested pipeline.
const C = { ice: "#DDE3E8", deep: "#C9D2DA", aub: "#3A0F34", soft: "#6B4A66", mari: "#EAA400", brk: "#C2362B", white: "#F4F6F8" };
const params = new URLSearchParams(location.search);
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches || params.has("still");
const film = params.has("film");
const sleep = ms => new Promise(r => setTimeout(r, reduced ? 0 : ms));
const fmt = (v, d = 1) => v.toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = v => fmt(v * 100, 2) + "%";
const $ = s => document.querySelector(s);

fetch("data.json?v=4").then(r => r.json()).then(D => {
  const scenes = { hero: hero(D), tower: tower(D), loans: loans(D), swaps: swaps(D), wall: wall(D), changes: changes(D), real: real(D) };
  // play each scene once when it comes into view
  const seen = new Set();
  const io = new IntersectionObserver(es => es.forEach(e => {
    if (e.isIntersecting && !seen.has(e.target.id) && scenes[e.target.id] && !film) { seen.add(e.target.id); scenes[e.target.id].enter?.(); }
  }), { threshold: 0.45 });
  Object.keys(scenes).forEach(id => io.observe(document.getElementById(id)));
  if (film) runFilm(scenes);
});

/* ---------------------------------------------------------------- hero */
function hero(D) {
  const h = D.hero;
  const li = ([k, v]) => `<li><span>${k}</span><span>${fmt(v)}</span></li>`;
  $("#assets").innerHTML = h.assets.map(li).join("");
  $("#liabilities").innerHTML = h.liabilities.map(li).join("");
  $("#total").textContent = fmt(h.total);
  $("#rules-total").textContent = h.rules_passed;
  const isRatio = l => /ratio/i.test(l);
  $("#cells").innerHTML = h.cells.map(([t, r, l, v]) =>
    `<li><span class="code">${t} ${r}</span><span class="label">${l}</span><span class="val">${isRatio(l) ? pct(v) : "€" + fmt(v) + "m"}</span></li>`).join("");
  let done = false;
  async function enter() {
    if (done) return; done = true;
    const from = $("#total").getBoundingClientRect();
    const cells = [...document.querySelectorAll("#cells li")];
    for (const [i, li] of cells.entries()) {
      if (!reduced) {
        const to = li.getBoundingClientRect();
        const f = document.createElement("span");
        f.className = "flyer"; f.textContent = li.querySelector(".val").textContent;
        f.style.left = from.left + "px"; f.style.top = from.top + "px";
        document.body.appendChild(f);
        f.animate([{ transform: "translate(0,0)", opacity: 1, filter: "blur(0)" },
                   { opacity: 1, filter: "blur(3px)", offset: .5 },
                   { transform: `translate(${to.left - from.left + 12}px,${to.top - from.top + 50}px)`, opacity: 0, filter: "blur(0)" }],
                  { duration: 650, easing: "cubic-bezier(.6,0,.3,1)" }).finished.then(() => f.remove());
        await sleep(330);
      }
      li.classList.add("filled");
    }
    await sleep(500);
    countUp($("#rules-passed"), D.hero.rules_passed, 900);
    $("#hero-stamp").classList.add("on");
  }
  return { enter };
}
function countUp(el, n, ms) {
  if (reduced) { el.textContent = n; return; }
  const t0 = performance.now();
  const tick = t => { const k = Math.min(1, (t - t0) / ms); el.textContent = Math.round(n * k * k * (3 - 2 * k)); if (k < 1) requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
}

/* ---------------------------------------------------------------- capital tower */
function tower(D) {
  const T = D.tower, svg = d3.select("#tower-svg"), H = 440, top = 40;
  const capital = [["CET1", T.cet1, C.aub], ["AT1", T.at1, C.soft], ["Tier 2", T.t2, "#9C7E98"]];
  const total = T.cet1 + T.at1 + T.t2;
  const max = 0.26 * T.trea;
  const y = d3.scaleLinear([0, max], [0, H]);
  const g = svg.append("g").attr("transform", `translate(0,${top})`);
  let acc = 0;
  capital.forEach(([n, v, col]) => {
    const h = y(v), yy = H - y(acc) - h;
    g.append("rect").attr("x", 40).attr("width", 150).attr("y", yy).attr("height", h).attr("fill", col);
    if (h > 22) g.append("text").attr("x", 52).attr("y", yy + 22).attr("fill", C.ice).style("fill", C.ice).attr("font-weight", 700).text(`${n}  €${fmt(v, 0)}m`);
    acc += v;
  });
  g.append("text").attr("x", 40).attr("y", H + 26).attr("font-weight", 700).text("Own funds");
  const reqTotal = g.append("text").attr("x", 470).attr("font-family", "JetBrains Mono").attr("font-size", 13).attr("fill", C.aub);
  g.append("text").attr("x", 40).attr("y", -12).attr("font-family", "JetBrains Mono").text(`${pct(total / T.trea)} of risk`);
  const req = g.append("g");
  const reqLabel = g.append("text").attr("x", 290).attr("y", H + 26).attr("font-weight", 700).text("Requirements");
  const line = g.append("line").attr("x1", 20).attr("x2", 600).attr("stroke", C.mari).attr("stroke-width", 3).attr("stroke-dasharray", "6 5");
  function draw(ccyb, animate) {
    const layers = [["Pillar 1", T.pillar1], ["Pillar 2 requirement", T.p2r], ["Conservation buffer", T.ccb], ["Countercyclical buffer", ccyb], ["Pillar 2 guidance", T.p2g]];
    let a = 0;
    const rows = layers.map(([n, r], i) => { const o = { n, r, y0: a, i }; a += r; return o; });
    const sel = req.selectAll("g.l").data(rows, d => d.n);
    const en = sel.enter().append("g").attr("class", "l");
    en.append("rect").attr("x", 290).attr("width", 150);
    en.append("text").attr("x", 450);
    const all = en.merge(sel);
    const tr = animate && !reduced ? d3.transition().duration(500) : null;
    const go = s => tr ? s.transition(tr) : s;
    go(all.select("rect")).attr("y", d => H - y((d.y0 + d.r) * T.trea)).attr("height", d => Math.max(0, y(d.r * T.trea) - 1))
      .attr("fill", d => d.n === "Countercyclical buffer" ? C.mari : d.i % 2 ? "#B7AFC0" : "#8E7F95");
    go(all.select("text")).attr("y", d => H - y((d.y0 + d.r / 2) * T.trea) + 5).text(d => `${d.n} ${pct(d.r)}`)
      .attr("font-size", 12);
    go(line).attr("y1", H - y(a * T.trea)).attr("y2", H - y(a * T.trea));
    reqTotal.attr("y", H - y(a * T.trea) - 8).text(`Asked for: ${pct(a)}`);
    const cbr = T.ccb + ccyb, cet1Need = (0.045 + 0.5625 * T.p2r + cbr) * T.trea;
    $("#surplus").textContent = "€" + fmt(T.cet1 - cet1Need, 1) + "m";
    $("#ccyb-out").textContent = pct(ccyb);
  }
  const input = $("#ccyb");
  input.addEventListener("input", () => draw(+input.value / 100, false));
  draw(T.ccyb, false);
  return {
    async filmPlay() {
      for (const v of [0, 0.5, 1.25, 2, 2.5, 1.5, 1]) { input.value = v; draw(v / 100, true); await sleep(650); }
    }
  };
}

/* ---------------------------------------------------------------- loans */
function loans(D) {
  const svg = d3.select("#dots-svg"), W = 640, H = 480;
  const names = ["Governments", "Banks", "Companies", "Retail", "Mortgages", "In default", "Other"];
  const color = d3.scaleLinear([0, 0.2, 0.75, 1, 1.5, 2.5], ["#F1E1B3", C.mari, "#B4708A", C.soft, C.aub, "#1E0619"]).clamp(true);
  const dots = D.dots.map(([c, rw, ev], i) => ({ c, rw, ev, i }));
  const cols = 80, cell = W / cols;
  const byWeight = [...dots].sort((a, b) => a.rw - b.rw || a.c - b.c);
  byWeight.forEach((d, i) => { d.wx = (i % cols) * cell + cell / 2; d.wy = Math.floor(i / cols) * cell + cell / 2; });
  // by class: one band per class
  const counts = d3.rollup(dots, v => v.length, d => d.c);
  let row0 = 0; const start = {};
  [...counts.keys()].sort().forEach(k => { start[k] = row0; row0 += Math.ceil(counts.get(k) / cols) + 1; });
  const idx = {};
  dots.forEach(d => { const n = idx[d.c] = (idx[d.c] ?? -1) + 1; d.cx2 = (n % cols) * cell + cell / 2; d.cy2 = (start[d.c] + Math.floor(n / cols)) * cell + cell / 2; });
  const scaleY = Math.min(1, H / (row0 * cell));
  const c = svg.append("g").selectAll("circle").data(dots).join("circle")
    .attr("r", cell * 0.44).attr("fill", d => color(d.rw)).attr("cx", d => d.wx).attr("cy", d => d.wy * scaleY);
  const leg = svg.append("g").attr("transform", `translate(0,${H + 26})`);
  [[0, "0%"], [0.2, "20%"], [0.75, "75%"], [1, "100%"], [1.5, "150%"], [2.5, "250%"]].forEach(([w, l], i) => {
    leg.append("circle").attr("cx", i * 78 + 6).attr("cy", 0).attr("r", 6).attr("fill", color(w));
    leg.append("text").attr("x", i * 78 + 18).attr("y", 4).attr("font-size", 12).text(l);
  });
  leg.append("text").attr("x", 480).attr("y", 4).attr("font-size", 12).text("risk weight");
  const labels = svg.append("g").attr("opacity", 0);
  [...counts.keys()].sort().forEach(k => labels.append("text").attr("x", W + 8).attr("y", (start[k] + 1) * cell * scaleY).attr("font-size", 12).attr("font-weight", 700).text(names[k]));
  function mode(m) {
    document.querySelectorAll("#loans .toggle button").forEach(b => b.setAttribute("aria-pressed", b.dataset.mode === m));
    const t = reduced ? c : c.transition().duration(900).delay(d => (d.i % cols) * 6);
    t.attr("cx", d => m === "weight" ? d.wx : d.cx2).attr("cy", d => (m === "weight" ? d.wy : d.cy2) * scaleY);
    labels.transition().duration(400).attr("opacity", m === "class" ? 1 : 0);
  }
  document.querySelectorAll("#loans .toggle button").forEach(b => b.addEventListener("click", () => mode(b.dataset.mode)));
  // the mortgage that splits
  const s = D.split, [sec, uns] = s.parts, loan = sec[1] + uns[1];
  $("#split").innerHTML = `<b>Mortgage loan-splitting, CRR Art 125.</b> €${fmt(loan, 2)}m loan on a €${fmt(s.value, 2)}m home: the part up to 55% of the value is weighted 20%, the rest 75%.
    <div class="bar-row"><div style="flex:${sec[1]};background:${C.mari}">20% · €${fmt(sec[1], 2)}m</div><div style="flex:${uns[1]};background:${C.soft};color:${C.ice}">75% · €${fmt(uns[1], 2)}m</div></div>
    <div class="legend"><span>Secured part, up to 55% of €${fmt(s.value, 2)}m</span><span>Remainder</span></div>`;
  return { async filmPlay() { await sleep(600); mode("class"); await sleep(2600); mode("weight"); await sleep(1200); } };
}

/* ---------------------------------------------------------------- derivatives waterfall */
function swaps(D) {
  const W = D.waterfall, svg = d3.select("#water-svg");
  const x = d3.scaleLog([10, 12000], [230, 620]);
  const yy = i => 20 + i * 64;
  svg.append("g").attr("class", "axis").attr("transform", `translate(0,${yy(W.length) - 10})`)
    .call(d3.axisBottom(x).tickValues([10, 100, 1000, 10000]).tickFormat(v => "€" + d3.format(",")(v) + "m"));
  const g = svg.selectAll("g.s").data(W).join("g").attr("class", "s").attr("transform", (d, i) => `translate(0,${yy(i)})`).attr("opacity", 0.15);
  g.append("text").attr("x", 0).attr("y", 24).attr("font-weight", 700).attr("font-size", 14).text(d => d[0]);
  g.append("rect").attr("x", 230).attr("y", 6).attr("height", 30).attr("width", 0).attr("fill", (d, i) => i === W.length - 1 ? C.mari : C.aub);
  g.append("text").attr("class", "v").attr("y", 26).attr("font-family", "JetBrains Mono").attr("font-weight", 600).attr("font-size", 13);
  let step = -1;
  function next() {
    step = (step + 1) % (W.length + 1);
    if (step === W.length) { step = -1; g.attr("opacity", 0.15).select("rect").attr("width", 0); g.select(".v").text(""); $("#step-text").textContent = ""; $("#step").textContent = "Next step"; return; }
    const sel = g.filter((d, i) => i === step).attr("opacity", 1);
    (reduced ? sel.select("rect") : sel.select("rect").transition().duration(600)).attr("width", d => x(Math.max(d[1], 10)) - 230);
    sel.select(".v").attr("x", d => x(Math.max(d[1], 10)) + 8).text(d => "€" + fmt(d[1], 1) + "m");
    const d = W[step];
    $("#step-text").innerHTML = `<b>€${fmt(d[1], 1)}m</b> ${d[2]}.`;
    $("#step").textContent = step === W.length - 1 ? "Start again" : "Next step";
  }
  $("#step").addEventListener("click", next);
  return { async filmPlay() { for (let i = 0; i < W.length; i++) { next(); await sleep(1600); } } };
}

/* ---------------------------------------------------------------- validation wall */
function wall(D) {
  const tiles = $("#tiles");
  tiles.innerHTML = D.wall.map(([id]) => `<span title="${id}" data-id="${id}"></span>`).join("");
  const byId = new Map([...tiles.children].map(t => [t.dataset.id, t]));
  const box = $("#scenarios");
  box.innerHTML = D.scenarios.map((s, i) => `<button data-i="${i}" aria-pressed="false">${s.label}</button>`).join("");
  function apply(i) {
    [...box.children].forEach(b => b.setAttribute("aria-pressed", b.dataset.i == i));
    byId.forEach(t => t.classList.remove("hit"));
    if (i == null) { $("#failed").innerHTML = ""; return; }
    const s = D.scenarios[i];
    s.failed.forEach(([id]) => byId.get(id)?.classList.add("hit"));
    $("#failed").innerHTML = `<li>Changed <b>${s.cell}</b>. ${s.failed.length} rule${s.failed.length > 1 ? "s" : ""} caught it:</li>` +
      s.failed.map(([id, e]) => `<li><b>${id}</b><code>${e}</code></li>`).join("");
  }
  box.addEventListener("click", e => { if (e.target.dataset.i != null) apply(+e.target.dataset.i); });
  $("#reset").addEventListener("click", () => apply(null));
  return { async filmPlay() { for (let i = 0; i < D.scenarios.length; i++) { apply(i); await sleep(2200); } apply(null); await sleep(600); } };
}

/* ---------------------------------------------------------------- change control */
function changes(D) {
  const box = $("#cr");
  function show(i) {
    document.querySelectorAll("#changes .toggle button").forEach(b => b.setAttribute("aria-pressed", b.dataset.cr == i));
    const cr = D.crs[i];
    const rows = Object.entries(D.cells_by_template).sort().map(([t, n]) => {
      const moved = cr.by_template[t] || 0;
      return `<div class="row"><code>${t.replace("_", " ").replace(".a", "")}</code><div class="cells">${
        Array.from({ length: n }, (_, k) => `<i class="${k < moved ? "moved" : ""}"></i>`).join("")}</div><span>${moved}</span></div>`;
    }).join("");
    box.innerHTML = `<div class="big">${cr.predicted} predicted.<br>${cr.changed} changed.<small>${cr.id}: ${cr.title}. Unexpected changes: 0.</small></div><div class="rows">${rows}</div>`;
  }
  document.querySelectorAll("#changes .toggle button").forEach(b => b.addEventListener("click", () => show(+b.dataset.cr)));
  show(0);
  return { async filmPlay() { await sleep(1800); show(1); await sleep(2600); } };
}

/* ---------------------------------------------------------------- real banks */
function real(D) {
  const R = D.real, svg = d3.select("#banks-svg"), W = 640, H = 360;
  $("#real-checks").textContent = R.checks.toLocaleString("en-GB");
  $("#real-breaks").textContent = R.breaks;
  const x = d3.scaleLinear([0.10, 0.40], [20, W - 60]).clamp(true);
  const pts = R.banks.map(([n, v, f]) => ({ n, v, f, tx: x(v), x: x(v), y: H / 2 })).sort((a, b) => a.v - b.v);
  const sim = d3.forceSimulation(pts).force("x", d3.forceX(d => d.tx).strength(0.9)).force("y", d3.forceY(H / 2).strength(0.06))
    .force("c", d3.forceCollide(7.5)).stop();
  for (let i = 0; i < 300; i++) sim.tick();
  svg.append("g").attr("class", "axis").attr("transform", `translate(0,${H + 10})`)
    .call(d3.axisBottom(x).ticks(6).tickFormat(d3.format(".0%")));
  svg.append("text").attr("x", W - 52).attr("y", H + 44).attr("font-size", 12).text("above 40% →");
  svg.append("text").attr("x", 20).attr("y", H + 44).attr("font-size", 12).text("CET1 ratio, June 2025");
  const finding = name => R.findings.find(([n]) => n === name);
  const dots = svg.append("g").selectAll("circle").data(pts).join("circle")
    .attr("cx", d => d.x).attr("cy", d => d.y).attr("r", 6.5)
    .attr("fill", d => d.f ? C.white : C.aub).attr("stroke", d => d.f ? C.brk : "none").attr("stroke-width", 3)
    .attr("tabindex", d => d.f ? 0 : null).style("cursor", d => d.f ? "pointer" : "default");
  dots.append("title").text(d => `${d.n}: ${pct(d.v)}`);
  function open(d) {
    const f = finding(d.n);
    if (!f) return;
    dots.attr("r", p => p === d ? 10 : 6.5);
    $("#finding").innerHTML = `<h3>${d.n}</h3><p>CET1 ratio ${pct(d.v)}. ${f[1]}</p>`;
  }
  dots.filter(d => d.f).on("click", (e, d) => open(d)).on("keydown", (e, d) => { if (e.key === "Enter") open(d); });
  return { async filmPlay() { for (const d of pts.filter(p => p.f)) { open(d); await sleep(2300); } } };
}

/* ---------------------------------------------------------------- film mode: one clean take for screen recording */
async function runFilm(scenes) {
  document.body.classList.add("film");
  const go = async id => { document.getElementById(id).scrollIntoView({ behavior: "smooth" }); await sleep(1400); };
  await sleep(1200);
  await scenes.hero.enter(); await sleep(2500);
  for (const id of ["tower", "loans", "swaps", "wall", "changes", "real"]) { await go(id); await scenes[id].filmPlay(); await sleep(800); }
  document.querySelector(".end").scrollIntoView({ behavior: "smooth" });
}
