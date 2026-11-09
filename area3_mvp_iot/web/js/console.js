// Margem — console da Defesa Civil. Rotas: #/entrar, #/fila, #/checkins, #/alertas, #/dashboard, #/estacoes
import { apiPara } from "./api.js";
import { $, $$, esc, html, raw, render, ico, injetarIcones, avisar, metros, n0, n1, hora, ha, dataHora, duracao, etiquetaNivel, debounce } from "./ui/util.js";
import { ROTULO, indice, CATEGORIA, VULNERAVEL, STATUS_OC, CENARIOS, TENDENCIA } from "./niveis.js";
import { criarRegua } from "./ui/regua.js";
import { criarMapa } from "./ui/mapa.js";
import { sparkline, linhaNivel, barrasEmpilhadas, colunas } from "./ui/graficos.js";

const api = apiPara("console");
const C = {
  territorio: null, risco: [], estacoes: [], series: {}, ocorrencias: [], checkins: [], alertas: [], cenario: null, usuario: null,
  rota: null, sel: null, novos: new Set(), filaLidaEm: 0, filtroFila: { status: "ativas", bairro: "" }, soAjuda: false,
  dash: { bairro_id: "", estacao_id: "", periodo: "30d" }, mapaDash: null, reguas: {}, log: [], rascunho: null,
};
const raiz = $("#raiz");
const bairro = (id) => C.territorio.bairros.find((b) => b.id === id);
const estacao = (id) => C.territorio.estacoes.find((e) => e.id === id);
const riscoDe = (id) => C.risco.find((r) => r.bairro_id === id);
const agoraMs = () => api.agora().getTime();
const anunciar = (t, urgente = false) => { const el = $(urgente ? "#anuncio-urgente" : "#anuncio"); el.textContent = ""; setTimeout(() => (el.textContent = t), 60); };

const MARCA = `<svg viewBox="0 0 26 30" aria-hidden="true"><rect x="5" y="1" width="12" height="28" fill="#E8E4DA" stroke="#E8E4DA" stroke-width="1.6"/><path d="M5 4h7M5 8h7M5 12h7" stroke="#0B141B" stroke-width="2"/><path d="M17 16h-7M17 20h-7" stroke="#C21F3A" stroke-width="2"/><path d="M1 23c3 0 3-2 6-2s3 2 6 2 3-2 6-2 3 2 6 2v6H1z" fill="#4FA3BF" opacity=".9"/></svg>`;

// ---------- Inicialização ----------
async function iniciar() {
  injetarIcones();
  await api.iniciar();
  C.territorio = await api.territorio();
  C.usuario = api.usuario();
  if (C.usuario) { try { C.usuario = await api.eu(); } catch { api.sair(); C.usuario = null; } }
  if (C.usuario && C.usuario.papel !== "defesa_civil") { api.sair(); C.usuario = null; }
  api.on(aoEvento);
  addEventListener("hashchange", rotear);
  if (C.usuario) await carregarTudo();
  rotear();
  setInterval(() => { if (C.usuario && api.modo === "real") carregarTudo().then(() => { renderFaixa(); atualizarRota(); }); }, 30000);
}

async function carregarTudo() {
  const [risco, estacoes, ocorrencias, checkins, alertas, cen] = await Promise.all([
    api.riscoAtual(), api.estacoes(), api.ocorrencias(), api.checkins(), api.alertas(), api.cenarioAtual(),
  ].map((p) => p.catch(() => null)));
  C.risco = risco ?? C.risco; C.estacoes = estacoes ?? C.estacoes; C.ocorrencias = ocorrencias ?? C.ocorrencias;
  C.checkins = checkins ?? C.checkins; C.alertas = alertas ?? C.alertas; if (cen) C.cenario = cen.cenario;
}

// ---------- Eventos em tempo real ----------
const recarregarRota = debounce(() => atualizarRota(), 250);
function aoEvento({ tipo, dados }) {
  if (!C.usuario) return;
  switch (tipo) {
    case "risco": {
      if (!Array.isArray(dados)) break;
      const mudou = dados.some((r) => riscoDe(r.bairro_id)?.nivel !== r.nivel);
      C.risco = dados; renderFaixa();
      // a prioridade depende do risco do bairro e do tempo de espera: relê a fila quando o nível muda (ou a cada 15 s)
      if (mudou || Date.now() - C.filaLidaEm > 15000) {
        C.filaLidaEm = Date.now();
        api.ocorrencias().then((l) => { C.ocorrencias = l; ordenarFila(); renderContadores(); recarregarRota(); }).catch(() => recarregarRota());
      } else recarregarRota();
      break;
    }
    case "leitura": {
      const e = C.estacoes.find((x) => x.id === dados.estacao_id);
      if (e) { e.ultima_leitura = dados; e.bateria_pct = dados.bateria_pct; }
      (C.series[dados.estacao_id] ??= []).push({ ts: dados.ts, nivel_cm: dados.nivel_cm });
      if (C.series[dados.estacao_id].length > 288) C.series[dados.estacao_id].shift();
      C.log.unshift(dados); C.log = C.log.slice(0, 40);
      if (api.modo === "real") recarregarRota();
      break;
    }
    case "ocorrencia": {
      const i = C.ocorrencias.findIndex((o) => o.id === dados.id);
      if (i >= 0) C.ocorrencias[i] = dados;
      else {
        C.ocorrencias.unshift(dados); C.novos.add(dados.id);
        avisar(`Nova ocorrência · prioridade ${dados.triagem.prioridade} · ${bairro(dados.bairro_id)?.nome}`, { icone: "inbox" });
        anunciar(`Nova ocorrência com prioridade ${dados.triagem.prioridade} no ${bairro(dados.bairro_id)?.nome}: ${dados.triagem.resumo}`, dados.triagem.prioridade >= 70);
      }
      ordenarFila(); renderContadores(); if (C.rota === "fila") renderFila(); if (C.rota === "dashboard") recarregarRota();
      break;
    }
    case "checkin":
      C.checkins.unshift(dados); renderContadores();
      if (dados.status === "preciso_ajuda") {
        avisar(`${dados.nome} pediu ajuda · ${bairro(dados.bairro_id)?.nome ?? ""}`, { icone: "life-buoy", ms: 6000 });
        anunciar(`${dados.nome} pediu ajuda no ${bairro(dados.bairro_id)?.nome ?? "bairro"}.`, true);
      }
      if (C.rota === "checkins") renderCheckins();
      break;
    case "alerta": C.alertas = [dados, ...C.alertas.filter((a) => a.id !== dados.id)]; if (C.rota === "alertas") renderHistoricoAlertas(); break;
    case "cenario": C.cenario = dados.cenario; renderCenarioAtual(); break;
    case "conexao": $("#conexao") && ($("#conexao").textContent = dados.offline ? "sem conexão" : "ao vivo"); break;
  }
}
function ordenarFila() {
  const ordem = { aberta: 0, em_atendimento: 1, resolvida: 2 };
  C.ocorrencias.sort((a, b) => ordem[a.status] - ordem[b.status] || b.triagem.prioridade - a.triagem.prioridade || a.criado_em.localeCompare(b.criado_em));
}

// ---------- Roteador ----------
const ROTAS = {
  fila: ["Fila de ocorrências", "inbox", telaFila],
  checkins: ["Check-ins", "users", telaCheckins],
  alertas: ["Alertas", "megaphone", telaAlertas],
  dashboard: ["Dashboard", "layout-dashboard", telaDashboard],
  estacoes: ["Estações IoT", "radio-tower", telaEstacoes],
};
async function rotear() {
  let rota = (location.hash.match(/^#\/(\w+)/) || [])[1];
  if (!C.usuario) { rota = "entrar"; if (location.hash !== "#/entrar") history.replaceState(null, "", "#/entrar"); return telaEntrar(); }
  if (!ROTAS[rota]) { rota = "fila"; history.replaceState(null, "", "#/fila"); }
  if (!$(".casca")) montarCasca();
  if (C.mapaDash && rota !== "dashboard") { C.mapaDash.mapa.remove(); C.mapaDash = null; }
  if (rota !== "estacoes") C.reguas = {};
  C.rota = rota;
  const [titulo] = ROTAS[rota];
  document.title = `Margem — ${titulo}`;
  $("#titulo").textContent = titulo;
  $$(".menu a").forEach((a) => (a.dataset.rota === rota ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  await ROTAS[rota][2]();
  $("#conteudo").focus({ preventScroll: true });
}
function atualizarRota() {
  if (C.rota === "fila") renderFila();
  else if (C.rota === "estacoes") atualizarEstacoes();
  else if (C.rota === "dashboard") renderDashboard();
  else if (C.rota === "alertas") atualizarRiscoSel();
  else if (C.rota === "checkins") renderCheckins();
}

function montarCasca() {
  render(raiz, html`<div class="casca">
    <aside class="lateral">
      <a class="marca" href="#/fila">${raw(MARCA)}<span><b>Margem</b><small>Defesa Civil · Zona Leste</small></span></a>
      <nav class="menu" aria-label="Seções do console">
        ${Object.entries(ROTAS).map(([k, [t, i]]) => html`<a href="#/${k}" data-rota="${k}">${ico(i)}<span>${t}</span>${raw(k === "fila" ? '<span class="cont" id="cont-fila"></span>' : k === "checkins" ? '<span class="cont" id="cont-ck"></span>' : "")}</a>`)}
      </nav>
      <div class="pe">
        <div class="relogio"><span class="vivo" aria-hidden="true"></span><span id="relogio">--:--</span><span id="conexao">ao vivo</span></div>
        <div id="cen-lateral"></div>
        ${api.modo === "demo" ? html`<span class="selo-demo">Modo demonstração — dados simulados no navegador</span>` : ""}
        <div><div class="op">${C.usuario.nome}</div><button class="btn btn-p btn-fantasma" id="sair" type="button">${ico("log-out", "ico-s")}Sair</button></div>
      </div>
    </aside>
    <div class="principal">
      <header class="topo-c"><div><h1 id="titulo"></h1><div class="ctx" id="ctx"></div></div><div class="faixa-risco" id="faixa" aria-label="Risco atual por bairro"></div></header>
      <main class="conteudo-c" id="conteudo" tabindex="-1"></main>
    </div>
  </div>
  <dialog class="confirma" id="dlg-confirma"><form method="dialog"><h2 id="cf-t"></h2><p id="cf-m"></p><div class="acoes"><button class="btn" value="nao">Cancelar</button><button class="btn btn-perigo" value="sim" id="cf-ok"></button></div></form></dialog>`);
  $("#sair").addEventListener("click", () => { api.sair(); C.usuario = null; location.hash = "#/entrar"; });
  setInterval(() => { const r = $("#relogio"); if (r) r.textContent = api.agora().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }); }, 1000);
  renderFaixa(); renderContadores(); renderCenarioAtual();
}

function renderFaixa() {
  const f = $("#faixa"); if (!f) return;
  f.innerHTML = String(html`${C.territorio.bairros.map((b) => {
    const r = riscoDe(b.id); if (!r) return "";
    const seta = r.tendencia === "subindo" ? "↑" : r.tendencia === "descendo" ? "↓" : "→";
    return html`<div class="fr-item" data-n="${indice(r.nivel)}" title="${b.nome}: ${ROTULO[r.nivel]}, chance de transbordo em 2 h ${Math.round(r.prob * 100)}%"><span class="fr-nome">${b.nome}</span><span class="fr-val">${r.nivel_cm != null ? metros(r.nivel_cm) : "—"} ${seta} · ${Math.round(r.prob * 100)}%</span>${etiquetaNivel(r.nivel)}</div>`;
  })}`);
}
function renderContadores() {
  const ab = C.ocorrencias.filter((o) => o.status === "aberta").length;
  const seisH = agoraMs() - 6 * 3600e3;
  const aj = C.checkins.filter((c) => c.status === "preciso_ajuda" && new Date(c.criado_em).getTime() >= seisH).length;
  const cf = $("#cont-fila"), ck = $("#cont-ck");
  if (cf) { cf.textContent = ab || ""; cf.hidden = !ab; cf.classList.toggle("quente", C.ocorrencias.some((o) => o.status === "aberta" && o.triagem.prioridade >= 70)); }
  if (ck) { ck.textContent = aj || ""; ck.hidden = !aj; ck.classList.toggle("quente", aj > 0); }
}
function renderCenarioAtual() {
  const el = $("#cen-lateral");
  if (el && C.cenario) el.innerHTML = String(html`<span class="selo">${ico("cloud-rain")}Cenário: ${CENARIOS[C.cenario]?.rotulo ?? C.cenario}</span>`);
  $$(".cen-btn").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.c === C.cenario)));
}

function confirmar(titulo, msg, ok) {
  const d = $("#dlg-confirma");
  $("#cf-t").textContent = titulo; $("#cf-m").textContent = msg; $("#cf-ok").textContent = ok;
  d.returnValue = ""; d.showModal();
  return new Promise((r) => { d.onclose = () => r(d.returnValue === "sim"); });
}

// ---------- Entrar ----------
function telaEntrar() {
  render(raiz, html`<div class="auth-c">
    <section class="lado">
      ${raw(`<a class="marca-auth" href="index.html">${MARCA}<b>Margem</b></a>`)}
      <div><h1>Console da Defesa Civil</h1><p>Fila de ocorrências priorizada por IA, pedidos de ajuda dos moradores, alertas e o nível do Tietê em tempo real em Jardim Pantanal, Vila Itaim, Jardim Romano e Jardim Helena.</p></div>
      <ul><li>${ico("inbox")}Relatos triados por agentes de IA, com fontes</li><li>${ico("radio-tower")}4 estações IoT medindo rio, chuva e solo</li><li>${ico("megaphone")}Alerta por app e SMS revisado por um operador</li></ul>
    </section>
    <section class="form-lado">
      <h2>Entrar</h2>
      <form class="form" id="f-entrar" novalidate>
        <div class="campo"><label for="email">E-mail institucional</label><input class="entrada" id="email" type="email" autocomplete="username" required></div>
        <div class="campo"><label for="senha">Senha</label><input class="entrada" id="senha" type="password" autocomplete="current-password" required></div>
        <div id="erro" role="alert"></div>
        <button class="btn btn-primario" type="submit">Entrar no console</button>
      </form>
      ${api.modo === "demo" ? html`<div class="demo-caixa"><span>Operador de demonstração: <span class="mono">operador@demo.margem.app</span> · <span class="mono">DefesaCivil@2026</span></span><button class="btn btn-p" id="demo" type="button">${ico("user", "ico-s")}Usar conta de demonstração</button><span class="selo-demo">Modo demonstração — dados simulados no navegador</span></div>` : ""}
      <p class="ctx"><a href="app.html">Sou morador</a></p>
    </section>
  </div>`);
  $("#demo")?.addEventListener("click", () => { $("#email").value = "operador@demo.margem.app"; $("#senha").value = "DefesaCivil@2026"; $("#f-entrar button").focus(); });
  $("#f-entrar").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const bt = $("#f-entrar button"); bt.classList.add("carregando");
    try {
      const r = await api.login($("#email").value.trim(), $("#senha").value);
      if (r.usuario.papel !== "defesa_civil") { api.sair(); throw new Error("Esta conta é de morador. O console é só para a Defesa Civil."); }
      C.usuario = r.usuario;
      await carregarTudo();
      location.hash = "#/fila";
    } catch (e) { $("#erro").innerHTML = `<p class="alerta-erro">${ico("triangle-alert")}${esc(e.message)}</p>`; }
    finally { bt.classList.remove("carregando"); }
  });
}

// ---------- Fila ----------
function telaFila() {
  ordenarFila();
  render($("#conteudo"), html`<div class="barra-filtros">
      <div class="seg" role="group" aria-label="Status" id="seg-status">
        ${[["ativas", "Abertas e em atendimento"], ["aberta", "Abertas"], ["em_atendimento", "Em atendimento"], ["resolvida", "Resolvidas"], ["todas", "Todas"]].map(([k, t]) => html`<button type="button" data-s="${k}" aria-pressed="${String(C.filtroFila.status === k)}">${t} <span class="n" data-n="${k}"></span></button>`)}
      </div>
      <select class="entrada" id="f-bairro" aria-label="Filtrar por bairro"><option value="">Todos os bairros</option>${C.territorio.bairros.map((b) => html`<option value="${b.id}" ${raw(C.filtroFila.bairro === b.id ? "selected" : "")}>${b.nome}</option>`)}</select>
    </div>
    <div class="fila-grade">
      <section class="painel"><div class="tabela-wrap" id="tabela-fila"></div></section>
      <aside class="painel detalhe" id="detalhe" aria-live="polite"></aside>
    </div>`);
  $$("#seg-status button").forEach((b) => b.addEventListener("click", () => { C.filtroFila.status = b.dataset.s; $$("#seg-status button").forEach((x) => x.setAttribute("aria-pressed", String(x === b))); renderFila(); }));
  $("#f-bairro").addEventListener("change", (e) => { C.filtroFila.bairro = e.target.value; renderFila(); });
  if (!C.sel) C.sel = C.ocorrencias.find((o) => o.status === "aberta")?.id ?? null;
  renderFila(); renderDetalhe();
}

function filtrarFila() {
  const { status, bairro: b } = C.filtroFila;
  return C.ocorrencias.filter((o) => (!b || o.bairro_id === b) && (status === "todas" || (status === "ativas" ? o.status !== "resolvida" : o.status === status)));
}
function renderFila() {
  const caixa = $("#tabela-fila"); if (!caixa) return;
  const lista = filtrarFila();
  const ab = C.ocorrencias.filter((o) => o.status === "aberta");
  $("#ctx").textContent = `${ab.length} aberta${ab.length === 1 ? "" : "s"} · ordenada pela prioridade calculada pela IA · ${ha(C.ocorrencias[0]?.criado_em ?? new Date(), agoraMs()) === "agora" ? "nova agora" : "atualiza ao vivo"}`;
  const conta = { ativas: 0, aberta: 0, em_atendimento: 0, resolvida: 0, todas: 0 };
  C.ocorrencias.filter((o) => !C.filtroFila.bairro || o.bairro_id === C.filtroFila.bairro).forEach((o) => { conta[o.status]++; conta.todas++; if (o.status !== "resolvida") conta.ativas++; });
  $$("#seg-status .n").forEach((n) => (n.textContent = conta[n.dataset.n]));
  if (!lista.length) { caixa.innerHTML = String(html`<div class="estado">${ico("inbox")}<strong>Nenhuma ocorrência aqui</strong><p>Quando um morador relatar algo, a IA classifica e o relato entra nesta fila por prioridade.</p></div>`); return; }
  const agora = agoraMs();
  caixa.innerHTML = String(html`<table class="tabela" aria-label="Ocorrências">
    <thead><tr><th class="col-prio" scope="col">Prioridade</th><th scope="col">Ocorrência</th><th scope="col">Gravidade</th><th scope="col">Vulneráveis</th><th scope="col">Espera</th><th scope="col">Status</th></tr></thead>
    <tbody>${lista.map((o) => {
      const t = o.triagem, p = t.prioridade;
      const esp = (((o.atendido_em ? new Date(o.atendido_em).getTime() : agora) - new Date(o.criado_em).getTime()) / 60000);
      const q = o.status === "aberta" ? (esp >= 60 ? 2 : esp >= 30 ? 1 : 0) : 0;
      const cls = [o.status === "resolvida" ? "resolvida" : "", C.novos.has(o.id) ? "novo" : ""].join(" ");
      return html`<tr data-id="${o.id}" tabindex="0" class="${cls}" aria-selected="${String(C.sel === o.id)}">
        <td><div class="prio" data-f="${p >= 70 ? "alta" : p >= 45 ? "media" : "baixa"}"><b>${p}</b><span class="trilho"><i style="width:${raw(String(p))}%"></i></span></div></td>
        <td><div class="oc-resumo">${t.resumo}</div><div class="oc-texto">“${o.texto}”</div><div class="oc-meta">${o.id} · ${bairro(o.bairro_id)?.nome} · ${CATEGORIA[t.categoria] ?? t.categoria} · ${hora(o.criado_em)}</div></td>
        <td><span class="grav" data-g="${t.gravidade}" title="Gravidade ${t.gravidade} de 5">${raw([1, 2, 3, 4, 5].map((k) => `<i class="${k <= t.gravidade ? "on" : ""}"></i>`).join(""))}</span><span class="sr-only">Gravidade ${t.gravidade} de 5</span></td>
        <td><div class="vul">${(t.vulneraveis ?? []).map((v) => html`<span title="${VULNERAVEL[v] ?? v}">${{ idoso: "Idoso", pcd: "PcD", crianca: "Criança", gestante: "Gestante", acamado: "Acamado" }[v] ?? v}</span>`)}</div></td>
        <td><span class="espera" data-q="${q}">${duracao(esp)}</span></td>
        <td><span class="st" data-s="${o.status}">${STATUS_OC[o.status]}</span></td>
      </tr>`;
    })}</tbody></table>`);
  C.novos.clear();
  $$("tbody tr", caixa).forEach((tr) => {
    const sel = () => { C.sel = tr.dataset.id; $$("tbody tr", caixa).forEach((x) => x.setAttribute("aria-selected", String(x === tr))); renderDetalhe(); };
    tr.addEventListener("click", sel);
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sel(); } if (e.key === "ArrowDown") tr.nextElementSibling?.focus(); if (e.key === "ArrowUp") tr.previousElementSibling?.focus(); });
  });
  renderDetalhe(true);
}

let ultimoDetalhe = "";
function renderDetalhe(soSeMudou = false) {
  const d = $("#detalhe"); if (!d) return;
  const o = C.ocorrencias.find((x) => x.id === C.sel);
  if (!o) { d.innerHTML = String(html`<div class="estado">${ico("inbox")}<strong>Selecione uma ocorrência</strong><p>O detalhe mostra o relato, a decisão de cada agente de IA e as fontes usadas.</p></div>`); ultimoDetalhe = ""; return; }
  const chave = `${o.id}|${o.status}|${o.triagem.prioridade}`;
  if (soSeMudou && chave === ultimoDetalhe) return;
  ultimoDetalhe = chave;
  const t = o.triagem, b = bairro(o.bairro_id), r = riscoDe(o.bairro_id);
  d.innerHTML = String(html`
    <div class="painel-cab"><h2><span class="mono">${o.id}</span></h2><div class="dir"><span class="st" data-s="${o.status}">${STATUS_OC[o.status]}</span></div></div>
    <div class="d-sec">
      <p class="citacao">“${o.texto}”</p>
      <dl class="kv"><dt>Morador</dt><dd>${o.usuario_nome ?? "—"}${o.origem === "simulado" ? " (simulado)" : ""}</dd><dt>Bairro</dt><dd>${b?.nome} ${r ? etiquetaNivel(r.nivel) : ""}</dd><dt>Recebida</dt><dd>${dataHora(o.criado_em)} · ${ha(o.criado_em, agoraMs())}</dd>${o.lat ? html`<dt>Local</dt><dd class="mono">${o.lat.toFixed(4)}, ${o.lng.toFixed(4)}</dd>` : ""}</dl>
      <div class="acoes">
        ${o.status === "aberta" ? html`<button class="btn btn-primario" data-st="em_atendimento" type="button">${ico("play", "ico-s")}Iniciar atendimento</button>` : ""}
        ${o.status !== "resolvida" ? html`<button class="btn" data-st="resolvida" type="button">${ico("check", "ico-s")}Marcar resolvida</button>` : html`<button class="btn" data-st="aberta" type="button">${ico("refresh-cw", "ico-s")}Reabrir</button>`}
      </div>
    </div>
    <div class="d-sec">
      <h3>Triagem da IA</h3>
      <dl class="kv"><dt>Categoria</dt><dd>${CATEGORIA[t.categoria] ?? t.categoria}</dd><dt>Gravidade</dt><dd>${t.gravidade} de 5</dd><dt>Prioridade</dt><dd>${t.prioridade} de 100</dd><dt>Vulneráveis</dt><dd>${t.vulneraveis?.length ? t.vulneraveis.map((v) => VULNERAVEL[v] ?? v).join(", ") : "nenhum citado"}</dd><dt>Confiança</dt><dd>${Math.round((t.confianca ?? 0) * 100)}% · <span class="mono">${t.modo}</span></dd></dl>
    </div>
    <div class="d-sec"><h3>Rastro dos agentes</h3>${(t.rastro ?? []).map((p) => html`<div class="passo-ag">${ico({ triagem: "bot", protocolos: "book-open", prioridade: "gauge", resposta: "send" }[p.agente] ?? "cpu")}<div><b>${p.agente}</b><span class="ms">${p.ms} ms</span><p>${p.saida}</p></div></div>`)}</div>
    <div class="d-sec"><h3>Fontes consultadas</h3>${(t.fontes ?? []).map((f) => html`<div class="fonte"><span class="mono">${f.doc}</span> · <b>${f.titulo}</b><br>${f.trecho}</div>`)}</div>
    <div class="d-sec"><h3>Orientação enviada ao morador</h3><p>${t.orientacao}</p></div>`);
  $$("button[data-st]", d).forEach((bt) => bt.addEventListener("click", async () => {
    bt.classList.add("carregando");
    try {
      const nova = await api.atualizarOcorrencia(o.id, bt.dataset.st);
      const i = C.ocorrencias.findIndex((x) => x.id === nova.id); if (i >= 0) C.ocorrencias[i] = nova;
      ordenarFila(); renderContadores(); renderFila(); renderDetalhe();
      avisar(`${o.id}: ${STATUS_OC[nova.status].toLowerCase()}.`, { icone: "check", ms: 2500 });
    } catch (e) { avisar(e.message, { icone: "triangle-alert" }); bt.classList.remove("carregando"); }
  }));
}

// ---------- Check-ins ----------
function telaCheckins() {
  render($("#conteudo"), html`<div class="resumo-ck" id="resumo-ck"></div>
    <section class="painel">
      <div class="painel-cab"><h2>Respostas dos moradores</h2><div class="dir"><label class="selo"><input type="checkbox" id="so-ajuda" ${raw(C.soAjuda ? "checked" : "")}> Só pedidos de ajuda</label></div></div>
      <div class="tabela-wrap" id="tabela-ck"></div>
    </section>`);
  $("#so-ajuda").addEventListener("change", (e) => { C.soAjuda = e.target.checked; renderCheckins(); });
  renderCheckins();
}
function renderCheckins() {
  const caixa = $("#tabela-ck"); if (!caixa) return;
  const seisH = agoraMs() - 6 * 3600e3;
  const recentes = C.checkins.filter((c) => new Date(c.criado_em).getTime() >= seisH);
  const aj = recentes.filter((c) => c.status === "preciso_ajuda").length;
  $("#ctx").textContent = `${recentes.length} resposta${recentes.length === 1 ? "" : "s"} nas últimas 6 h · ${aj} pedido${aj === 1 ? "" : "s"} de ajuda · telefones mascarados (LGPD)`;
  $("#resumo-ck").innerHTML = String(html`${C.territorio.bairros.map((b) => {
    const l = recentes.filter((c) => c.bairro_id === b.id);
    const s = l.filter((c) => c.status === "seguro").length, a = l.length - s, tot = Math.max(1, l.length);
    const r = riscoDe(b.id);
    return html`<div class="painel rc"><div class="rc-nome"><span>${b.nome}</span>${r ? etiquetaNivel(r.nivel) : ""}</div>
      <div class="rc-barra" role="img" aria-label="${s} seguros e ${a} pedidos de ajuda"><i class="s" style="width:${raw(String((s / tot) * 100))}%"></i><i class="a" style="width:${raw(String((a / tot) * 100))}%"></i></div>
      <div class="rc-num"><span><b>${s}</b> seguros</span><span><b>${a}</b> pedem ajuda</span></div></div>`;
  })}`);
  const lista = C.checkins.filter((c) => !C.soAjuda || c.status === "preciso_ajuda").sort((x, y) => (y.status === "preciso_ajuda") - (x.status === "preciso_ajuda") || y.criado_em.localeCompare(x.criado_em));
  if (!lista.length) { caixa.innerHTML = String(html`<div class="estado">${ico("users")}<strong>${C.soAjuda ? "Nenhum pedido de ajuda" : "Nenhum check-in ainda"}</strong><p>Quando um alerta sai, os moradores respondem “Estou seguro” ou “Preciso de ajuda” pelo app.</p></div>`); return; }
  caixa.innerHTML = String(html`<table class="tabela"><thead><tr><th scope="col">Situação</th><th scope="col">Morador</th><th scope="col">Telefone</th><th scope="col">Bairro</th><th scope="col">Vulneráveis</th><th scope="col">Observação</th><th scope="col">Quando</th></tr></thead>
    <tbody>${lista.map((c) => html`<tr class="${c.status === "preciso_ajuda" ? "ajuda" : ""}">
      <td><span class="ck-st" data-s="${c.status}">${ico(c.status === "seguro" ? "shield-check" : "life-buoy")}${c.status === "seguro" ? "Seguro" : "Precisa de ajuda"}</span></td>
      <td>${c.nome ?? "Morador"}</td><td class="mono">${c.telefone_mascarado ?? "—"}</td><td>${bairro(c.bairro_id)?.nome ?? "—"}</td>
      <td><div class="vul">${(c.vulnerabilidades ?? []).map((v) => html`<span>${{ idoso: "Idoso", pcd: "PcD", crianca: "Criança", gestante: "Gestante", acamado: "Acamado" }[v] ?? v}</span>`)}</div></td>
      <td>${c.obs || "—"}</td><td class="mono">${hora(c.criado_em)} · ${ha(c.criado_em, agoraMs())}</td></tr>`)}</tbody></table>`);
}

// ---------- Alertas ----------
const GSM = new Set("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà^{}\\[~]|€");
function telaAlertas() {
  const pior = [...C.risco].sort((a, b) => indice(b.nivel) - indice(a.nivel) || b.prob - a.prob)[0];
  render($("#conteudo"), html`<div class="alertas-grade">
    <section class="painel">
      <div class="painel-cab"><h2>Novo alerta</h2><div class="dir">o agente redige, você revisa e emite</div></div>
      <form class="painel-corpo form-al" id="f-al" novalidate>
        <div class="campo"><label for="al-bairro">Bairro</label><select class="entrada" id="al-bairro">${C.territorio.bairros.map((b) => html`<option value="${b.id}" ${raw(b.id === pior?.bairro_id ? "selected" : "")}>${b.nome}</option>`)}</select></div>
        <div class="risco-sel" id="risco-sel"></div>
        <button class="btn" type="button" id="al-gerar">${ico("bot", "ico-s")}Gerar rascunho com o agente comunicador</button>
        <div id="al-rastro"></div>
        <div class="campo"><label for="al-titulo">Título</label><input class="entrada" id="al-titulo" maxlength="80"></div>
        <div class="campo"><label for="al-sms">SMS</label><textarea class="entrada" id="al-sms" rows="3"></textarea><div class="cont-sms" id="al-cont"><span></span><span></span></div><div class="trilho-sms"><i></i></div></div>
        <div class="campo"><label for="al-completa">Mensagem completa (app e voz)</label><textarea class="entrada" id="al-completa" rows="5"></textarea></div>
        <div id="al-erro" role="alert"></div>
        <div><button class="btn btn-perigo" type="submit">${ico("megaphone", "ico-s")}Revisar e emitir alerta</button></div>
      </form>
    </section>
    <div class="coluna-al">
      <section class="painel"><div class="painel-cab"><h2>Como o morador recebe</h2></div><div class="painel-corpo"><div class="celular" aria-label="Prévia no celular">
        <div class="cel-topo"><span id="pv-hora"></span><span>4G ▮▮▮</span></div>
        <div class="push"><span class="push-app">${ico("bell-ring", "ico-s")} MARGEM · agora</span><b id="pv-titulo">Título do alerta</b><span id="pv-push">A mensagem completa aparece aqui.</span></div>
        <div class="cel-de">SMS · Defesa Civil</div>
        <div><div class="bolha" id="pv-sms">O texto do SMS aparece aqui.</div><div class="bolha-hora" id="pv-sms-h"></div></div>
      </div></div></section>
      <section class="painel"><div class="painel-cab"><h2>Alertas emitidos</h2><div class="dir">válidos por 6 h</div></div><ul class="lista-al" id="lista-al"></ul></section>
    </div>
  </div>`);
  $("#al-bairro").addEventListener("change", () => { atualizarRiscoSel(); });
  $("#al-gerar").addEventListener("click", gerarRascunho);
  ["#al-titulo", "#al-sms", "#al-completa"].forEach((s) => $(s).addEventListener("input", atualizarPrevia));
  $("#f-al").addEventListener("submit", emitir);
  atualizarRiscoSel(); atualizarPrevia(); renderHistoricoAlertas();
}
function atualizarRiscoSel() {
  const el = $("#risco-sel"); if (!el) return;
  const r = riscoDe($("#al-bairro").value); if (!r) return;
  el.innerHTML = String(html`${etiquetaNivel(r.nivel)}<span>rio <b>${r.nivel_cm != null ? metros(r.nivel_cm) : "—"}</b> · ${TENDENCIA[r.tendencia] ?? r.tendencia} · chance 2 h <b>${Math.round(r.prob * 100)}%</b></span>`);
  $("#ctx").textContent = `${C.alertas.length} alerta${C.alertas.length === 1 ? "" : "s"} ativo${C.alertas.length === 1 ? "" : "s"} · ${C.risco.filter((x) => indice(x.nivel) >= 2).length} bairro(s) em Alerta ou acima`;
}
async function gerarRascunho() {
  const bt = $("#al-gerar"); bt.classList.add("carregando");
  $("#al-rastro").innerHTML = "";
  try {
    const r = await api.rascunhoAlerta($("#al-bairro").value);
    C.rascunho = r;
    $("#al-titulo").value = r.titulo; $("#al-sms").value = r.mensagem_curta; $("#al-completa").value = r.mensagem_completa;
    const passos = r.rastro?.length ? r.rastro : null;
    $("#al-rastro").innerHTML = String(html`${passos ? passos.map((p) => html`<div class="agente-linha">${ico("bot")}<span><b>${p.agente}</b> · <span class="mono">${p.ms} ms</span> · ${p.saida}</span></div>`) : html`<div class="agente-linha">${ico("bot")}<span>Rascunho gerado pelo agente comunicador. Revise antes de emitir.</span></div>`}`);
    atualizarPrevia();
  } catch (e) { avisar(e.message, { icone: "triangle-alert" }); }
  finally { bt.classList.remove("carregando"); }
}
function atualizarPrevia() {
  const t = $("#al-titulo").value.trim(), s = $("#al-sms").value, c = $("#al-completa").value.trim();
  const gsm = [...s].every((ch) => GSM.has(ch));
  const lim = 160;
  const est = s.length > lim ? "ruim" : s.length > lim - 15 ? "quase" : "ok";
  const cont = $("#al-cont");
  cont.dataset.estado = !gsm && s.length > 70 ? "ruim" : est;
  cont.children[0].textContent = gsm ? "GSM-7 · 1 SMS" : "Tem acento fora do padrão GSM: o limite cai para 70";
  cont.children[1].textContent = `${s.length}/${gsm ? lim : 70}`;
  $(".trilho-sms i").style.width = `${Math.min(100, (s.length / (gsm ? lim : 70)) * 100)}%`;
  $("#pv-titulo").textContent = t || "Título do alerta";
  $("#pv-push").textContent = c ? (c.length > 140 ? `${c.slice(0, 140)}…` : c) : "A mensagem completa aparece aqui.";
  $("#pv-sms").textContent = s || "O texto do SMS aparece aqui.";
  const h = hora(api.agora()); $("#pv-hora").textContent = h; $("#pv-sms-h").textContent = h;
}
async function emitir(ev) {
  ev.preventDefault();
  const b = bairro($("#al-bairro").value), r = riscoDe(b.id);
  const body = { bairro_id: b.id, nivel: C.rascunho?.bairro_id === b.id ? C.rascunho.nivel : r.nivel, titulo: $("#al-titulo").value.trim(), mensagem_curta: $("#al-sms").value.trim(), mensagem_completa: $("#al-completa").value.trim() };
  const err = $("#al-erro");
  if (!body.titulo || !body.mensagem_curta) { err.innerHTML = `<p class="alerta-erro">${ico("triangle-alert")}Gere o rascunho ou preencha título e SMS.</p>`; return; }
  if (body.mensagem_curta.length > 160) { err.innerHTML = `<p class="alerta-erro">${ico("triangle-alert")}O SMS passou de 160 caracteres.</p>`; return; }
  err.innerHTML = "";
  const ok = await confirmar(`Emitir “${ROTULO[body.nivel]}” para ${b.nome}?`, `O alerta vai por app, voz e SMS para todos os moradores cadastrados no ${b.nome}. Não dá para desfazer o envio do SMS.`, "Emitir agora");
  if (!ok) return;
  try {
    const al = await api.emitirAlerta(body);
    C.alertas = [al, ...C.alertas.filter((a) => a.id !== al.id)];
    renderHistoricoAlertas();
    avisar(`Alerta ${al.id} emitido para ${b.nome}${al.destinatarios ? ` · ${n0(al.destinatarios)} morador${al.destinatarios === 1 ? "" : "es"}` : ""}.`, { icone: "megaphone", ms: 5000 });
    $("#al-titulo").value = ""; $("#al-sms").value = ""; $("#al-completa").value = ""; $("#al-rastro").innerHTML = ""; C.rascunho = null; atualizarPrevia();
  } catch (e) { err.innerHTML = `<p class="alerta-erro">${ico("triangle-alert")}${esc(e.message)}</p>`; }
}
const ORIGEM_AL = { modelo: "automático (modelo de IA)", manual: "Defesa Civil", defesa_civil: "Defesa Civil" };
function renderHistoricoAlertas() {
  const ul = $("#lista-al"); if (!ul) return;
  if (!C.alertas.length) { ul.innerHTML = String(html`<li class="estado">${ico("megaphone")}<strong>Nenhum alerta ativo</strong><p>Gere um rascunho ao lado. O texto só sai depois da sua revisão.</p></li>`); return; }
  ul.innerHTML = String(html`${C.alertas.map((a) => html`<li>${etiquetaNivel(a.nivel)}<div><div class="t">${a.titulo}</div><div class="m">${a.id} · ${a.mensagem_curta.length} caracteres · ${ORIGEM_AL[a.origem] ?? a.origem}</div></div><div class="q">${hora(a.emitido_em)}<br>até ${hora(a.valido_ate)}</div></li>`)}`);
  atualizarRiscoSel();
}

// ---------- Dashboard ----------
const PERIODOS = { "24h": ["24 h", 1], "7d": ["7 dias", 7], "30d": ["30 dias", 30], "90d": ["90 dias", 90], "1a": ["1 ano", 365] };
const AGREGACAO = { "5min": "leituras a cada 5 min", "10min": "leituras a cada 10 min", "1h": "média por hora", "6h": "máximo a cada 6 h", max_diario: "máximo diário" };
function telaDashboard() {
  const d = C.dash;
  render($("#conteudo"), html`<div class="barra-filtros">
      <div class="seg" role="group" aria-label="Período" id="seg-per">${Object.entries(PERIODOS).map(([k, [t]]) => html`<button type="button" data-p="${k}" aria-pressed="${String(d.periodo === k)}">${t}</button>`)}</div>
      <select class="entrada" id="d-bairro" aria-label="Bairro"><option value="">Todos os bairros</option>${C.territorio.bairros.map((b) => html`<option value="${b.id}" ${raw(d.bairro_id === b.id ? "selected" : "")}>${b.nome}</option>`)}</select>
      <select class="entrada" id="d-est" aria-label="Estação"><option value="">Todas as estações</option>${C.territorio.estacoes.map((e) => html`<option value="${e.id}" ${raw(d.estacao_id === e.id ? "selected" : "")}>${e.nome}</option>`)}</select>
      <span class="ctx" id="d-gerado"></span>
    </div>
    <div id="dash"><div class="esqueleto esq-kpis"></div></div>`);
  $$("#seg-per button").forEach((b) => b.addEventListener("click", () => { d.periodo = b.dataset.p; $$("#seg-per button").forEach((x) => x.setAttribute("aria-pressed", String(x === b))); renderDashboard(true); }));
  $("#d-bairro").addEventListener("change", (e) => { d.bairro_id = e.target.value; renderDashboard(true); });
  $("#d-est").addEventListener("change", (e) => { d.estacao_id = e.target.value; renderDashboard(true); });
  renderDashboard(true);
}

let dashOcupado = false, dashUltimo = 0, dashPendente = false;
async function renderDashboard(forcar = false) {
  if (dashOcupado) { if (forcar) dashPendente = true; return; }
  if (!forcar && (Date.now() - dashUltimo < 5000 || document.querySelector(".formula:popover-open"))) return;
  dashOcupado = true; dashUltimo = Date.now();
  try {
    const d = C.dash;
    const ate = api.agora();
    const de = new Date(ate.getTime() - PERIODOS[d.periodo][1] * 864e5);
    const ind = await api.indicadores({ bairro_id: d.bairro_id || null, estacao_id: d.estacao_id || null, de: de.toISOString(), ate: ate.toISOString() });
    if (C.rota !== "dashboard") return;
    desenharDashboard(ind);
  } catch (e) {
    const el = $("#dash"); if (el) el.innerHTML = String(html`<div class="painel estado">${ico("triangle-alert")}<strong>Não deu para carregar os indicadores</strong><p>${e.message}</p></div>`);
  } finally { dashOcupado = false; if (dashPendente) { dashPendente = false; renderDashboard(true); } }
}

function infoFormula(chave, f) {
  if (!f) return "";
  return html`<button class="info-btn" type="button" popovertarget="fx-${chave}" aria-label="Como calculamos: ${f.titulo}">${ico("info", "ico-s")}</button>
    <div popover id="fx-${chave}" class="formula"><h3>${f.titulo}</h3><p>${f.formula}</p><span class="rot">Equivalente DAX (Power BI)</span><code>${f.dax}</code></div>`;
}

function desenharDashboard(ind) {
  const el = $("#dash"); if (!el) return;
  const k = ind.kpis, F = ind.formulas ?? {};
  $("#d-gerado").textContent = `atualizado ${hora(ind.gerado_em)}`;
  $("#ctx").textContent = `Indicadores · ${PERIODOS[C.dash.periodo][0]}${C.dash.bairro_id ? ` · ${bairro(C.dash.bairro_id).nome}` : ""}${C.dash.estacao_id ? ` · ${estacao(C.dash.estacao_id).nome}` : ""}`;
  const maxRisco = ind.risco_bairro[0];
  const cats = ind.ocorrencias.por_categoria.filter((c) => c.total).sort((a, b) => b.total - a.total);
  const coresG = ["#3C4F5B", "#5C7B8A", "#C9A24A", "#E07B3A", "#FF6B82"];
  const ant = ind.antecedencia;
  const maxAnt = Math.max(ant.modelo_min ?? 0, ant.cota_min ?? 0, 1);
  el.innerHTML = String(html`
    <div class="kpis">
      <div class="kpi"><div class="k-cab">Maior risco agora ${infoFormula("k1", F.risco_bairro)}</div><div class="k-val">${maxRisco ? ROTULO[maxRisco.nivel] : "—"}</div><div class="k-det">${maxRisco ? html`${maxRisco.nome} · <b>${Math.round(maxRisco.prob * 100)}%</b> em 2 h` : ""}</div></div>
      <div class="kpi"><div class="k-cab">Ocorrências ${infoFormula("k2", F.ocorrencias)}</div><div class="k-val">${n0(k.ocorrencias_periodo)}</div><div class="k-det"><b>${k.ocorrencias_abertas}</b> abertas agora</div></div>
      <div class="kpi"><div class="k-cab">Tempo até atendimento ${infoFormula("k3", F.tempo_atendimento)}</div><div class="k-val">${n1(k.tempo_medio_atendimento_min)}<small>min</small></div><div class="k-det"><b>${Math.round(k.pct_atendidas_30min * 100)}%</b> atendidas em até 30 min</div></div>
      <div class="kpi"><div class="k-cab">Vulneráveis em risco ${infoFormula("k4", F.vulneraveis)}</div><div class="k-val">${n0(k.vulneraveis_area_risco)}</div><div class="k-det"><b>${Math.round(k.pct_vulneraveis_checkin * 100)}%</b> já fizeram check-in</div></div>
      <div class="kpi"><div class="k-cab">Antecedência do alerta ${infoFormula("k5", F.antecedencia)}</div><div class="k-val">${k.antecedencia_modelo_min ?? "—"}<small>min</small></div><div class="k-det">só por cota: <b>${k.antecedencia_cota_min ?? "—"} min</b></div></div>
      <div class="kpi"><div class="k-cab">Nível vs cota ${infoFormula("k6", F.nivel_vs_cota)}</div><div class="k-val">${ind.nivel_vs_cota.length ? `${Math.round(Math.max(...ind.nivel_vs_cota.map((x) => x.pct_cota_atual)) * 100)}` : "—"}<small>%</small></div><div class="k-det">maior % da cota de alerta agora</div></div>
    </div>
    <div class="dash-grade">
      <section class="painel w8"><div class="painel-cab"><h2>1 · Nível vs cota por estação</h2>${infoFormula("g1", F.nivel_vs_cota)}<div class="dir">${AGREGACAO[ind.nivel_vs_cota[0]?.agregacao] ?? ""}</div></div>
        <div class="painel-corpo multiplos ${ind.nivel_vs_cota.length === 1 ? "um" : ""}">${ind.nivel_vs_cota.map((s) => html`<div><div class="mult-cab"><b>${s.nome}</b><span>${metros(s.nivel_atual_cm)} · ${Math.round(s.pct_cota_atual * 100)}% da cota</span></div>${raw(linhaNivel(s.serie, { w: ind.nivel_vs_cota.length === 1 ? 900 : 440, h: ind.nivel_vs_cota.length === 1 ? 260 : 170, cotaAlerta: s.cota_alerta_cm, cotaTransbordo: s.cota_transbordo_cm, agregacao: s.agregacao, titulo: `Nível da estação ${s.nome}` }))}</div>`)}</div></section>
      <section class="painel w4"><div class="painel-cab"><h2>2 · Risco previsto por bairro</h2>${infoFormula("g2", F.risco_bairro)}<div class="dir">próx. 2 h</div></div>
        <div class="painel-corpo"><ol class="ranking">${ind.risco_bairro.map((r) => html`<li data-n="${indice(r.nivel)}"><span class="rk-nome">${r.nome}</span>${etiquetaNivel(r.nivel)}<span class="rk-barra"><i style="width:${raw(String(Math.max(2, r.prob * 100)))}%"></i></span><span class="rk-p">${Math.round(r.prob * 100)}%</span></li>`)}</ol>
        <div id="mapa-slot"></div></div></section>
      <section class="painel w6"><div class="painel-cab"><h2>3 · Ocorrências por categoria e gravidade</h2>${infoFormula("g3", F.ocorrencias)}<div class="dir">${n0(ind.ocorrencias.total)} no período</div></div>
        <div class="painel-corpo">${cats.length ? raw(barrasEmpilhadas(cats.map((c) => ({ rotulo: CATEGORIA[c.categoria], valores: c.por_gravidade })), { chaves: [1, 2, 3, 4, 5], cores: coresG, rotulos: ["gravidade 1", "gravidade 2", "gravidade 3", "gravidade 4", "gravidade 5"] })) : html`<p class="g-vazio">Nenhuma ocorrência no período.</p>`}
          <div class="legenda-g">${coresG.map((c, i) => html`<span><i style="background:${raw(c)}"></i>gravidade ${i + 1}</span>`)}</div>
          <div class="status-linha"><span>Abertas <b>${ind.ocorrencias.por_status.aberta}</b></span><span>Em atendimento <b>${ind.ocorrencias.por_status.em_atendimento}</b></span><span>Resolvidas <b>${ind.ocorrencias.por_status.resolvida}</b></span></div></div></section>
      <section class="painel w6"><div class="painel-cab"><h2>4 · Tempo médio até atendimento</h2>${infoFormula("g4", F.tempo_atendimento)}<div class="dir">${ind.tempo_atendimento.agrupamento === "mes" ? "por mês" : "por semana"} · meta 30 min</div></div>
        <div class="painel-corpo">${raw(colunas(ind.tempo_atendimento.por_semana.map((s) => ({ rotulo: new Date(s.inicio).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }), valor: s.medio_min })), { meta: 30, sufixo: " min" }))}
          <div class="status-linha"><span>Média no período <b>${n1(ind.tempo_atendimento.medio_min)} min</b></span><span>Em até 30 min <b>${Math.round(ind.tempo_atendimento.pct_ate_30min * 100)}%</b></span></div></div></section>
      <section class="painel w6"><div class="painel-cab"><h2>5 · Vulneráveis em área de risco</h2>${infoFormula("g5", F.vulneraveis)}<div class="dir">bairros ≥ Alerta</div></div>
        <div class="painel-corpo"><div class="medidor-pct"><div class="mult-cab"><b>${n0(ind.vulneraveis.em_area_risco)} pessoas cadastradas como vulneráveis</b><span>${Math.round(ind.vulneraveis.pct_checkin * 100)}% com check-in</span></div><div class="mp-barra"><i style="width:${raw(String(ind.vulneraveis.pct_checkin * 100))}%"></i></div>
          <p class="k-det">${ind.vulneraveis.bairros_em_risco?.length ? `Em risco agora: ${ind.vulneraveis.bairros_em_risco.map((id) => bairro(id)?.nome).join(", ")}.` : ind.vulneraveis.total_cadastrados != null ? `Nenhum bairro em Alerta agora. ${n0(ind.vulneraveis.total_cadastrados)} pessoas vulneráveis cadastradas no total.` : "Nenhum bairro em Alerta agora. O total abaixo é a base cadastrada."}</p></div>
          <div class="por-tipo" ${raw(ind.vulneraveis.total_cadastrados != null && !ind.vulneraveis.em_area_risco ? "hidden" : "")}>${Object.entries(ind.vulneraveis.por_tipo).map(([t, v]) => html`<div><b>${v}</b><span>${VULNERAVEL[t] ?? t}</span></div>`)}</div></div></section>
      <section class="painel w6"><div class="painel-cab"><h2>6 · Antecedência do alerta</h2>${infoFormula("g6", F.antecedencia)}<div class="dir">${ant.eventos?.length ?? 0} transbordo${ant.eventos?.length === 1 ? "" : "s"} no período</div></div>
        <div class="painel-corpo comparar">
          <div class="cp-l"><span>Modelo de IA</span><span class="cp-b"><i style="width:${raw(String(((ant.modelo_min ?? 0) / maxAnt) * 100))}%" class="cp-modelo"></i></span><span class="cp-v">${ant.modelo_min ?? "—"} min</span></div>
          <div class="cp-l"><span>Só pela cota</span><span class="cp-b"><i style="width:${raw(String(((ant.cota_min ?? 0) / maxAnt) * 100))}%" class="cp-cota"></i></span><span class="cp-v">${ant.cota_min ?? "—"} min</span></div>
          <p class="k-det">${textoAntecedencia(ant)}</p>
        </div></section>
    </div>`);
  // mapa de risco: a mesma instância é reaproveitada entre atualizações (sem piscar)
  const slot = $("#mapa-slot");
  if (!C.mapaDash && window.L) {
    C.mapaEl = document.createElement("div");
    C.mapaEl.className = "mapa-dash"; C.mapaEl.setAttribute("aria-label", "Mapa de risco por bairro");
    slot.append(C.mapaEl);
    C.mapaDash = criarMapa(C.mapaEl, C.territorio, { tema: "escuro", mostrar: { bairros: true, estacoes: false, abrigos: true } });
    C.mapaDash?.mapa.setZoom(13);
  } else if (C.mapaEl) { slot.append(C.mapaEl); C.mapaDash.redimensionar(); }
  C.mapaDash?.atualizarRisco(C.risco);
}

function textoAntecedencia(ant) {
  if (ant.modelo_min == null || ant.cota_min == null || !(ant.eventos?.length ?? ant.transbordos)) return "Sem transbordos no período filtrado.";
  const ganho = ant.ganho_min ?? ant.modelo_min - ant.cota_min;
  const fim = " Histórico simulado de 1 ano.";
  if (ganho > 0) return html`O modelo avisa em média <b>${ganho} min antes</b> do que a regra que só olha a cota da régua.${fim}`;
  if (ganho === 0) return html`No período, o modelo e a regra da cota avisaram com a mesma antecedência.${fim}`;
  return html`No período, a regra da cota avisou <b>${-ganho} min antes</b> do que o modelo.${fim}`;
}

// ---------- Estações IoT ----------
async function telaEstacoes() {
  render($("#conteudo"), html`<section class="painel">
      <div class="painel-cab"><h2>Cenário de simulação</h2><div class="dir">${api.modo === "demo" ? "simulação no navegador · 1 leitura a cada 3 s = 5 min de rio" : "comando enviado ao simulador das estações"}</div></div>
      <div class="painel-corpo cenario">
        <div class="cenario-op" role="group" aria-label="Cenário">${Object.entries(CENARIOS).map(([k, c]) => html`<button type="button" class="cen-btn" data-c="${k}" aria-pressed="${String(C.cenario === k)}"><b>${ico({ normal: "sun", chuva_forte: "cloud-rain", enchente: "waves", recuperacao: "sprout" }[k], "ico-s")}${c.rotulo}</b><span>${c.desc}</span></button>`)}</div>
        <p class="cen-info">Use durante a apresentação: o nível sobe nas réguas, o risco muda, a fila recebe relatos e os moradores recebem o alerta.</p>
      </div>
    </section>
    <div class="estacoes" id="estacoes"></div>
    <section class="painel"><div class="painel-cab"><h2>Leituras recebidas</h2><div class="dir">MQTT/HTTP assinadas com HMAC · ao vivo</div></div><div class="log" id="log"></div></section>`);
  $$(".cen-btn").forEach((b) => b.addEventListener("click", async () => {
    try { const r = await api.cenario(b.dataset.c); C.cenario = r?.cenario ?? b.dataset.c; renderCenarioAtual(); avisar(`Cenário: ${CENARIOS[C.cenario].rotulo}.`, { icone: "cloud-rain", ms: 2500 }); }
    catch (e) { avisar(e.message, { icone: "triangle-alert" }); }
  }));
  await Promise.all(C.territorio.estacoes.map(async (e) => { if (!C.series[e.id]?.length) C.series[e.id] = (await api.leituras(e.id, 24).catch(() => [])).map((p) => ({ ts: p.ts, nivel_cm: p.nivel_cm })); }));
  if (!C.log.length) C.log = C.territorio.estacoes.map((e) => C.estacoes.find((x) => x.id === e.id)?.ultima_leitura).filter(Boolean);
  if (C.rota !== "estacoes") return;
  $("#estacoes").innerHTML = String(html`${C.territorio.estacoes.map((e) => html`<article class="painel est" data-id="${e.id}">
    <div class="est-regua" id="rg-${e.id}"></div>
    <div class="est-cab"><b>${e.nome}</b><span class="mono">${e.id} · ${bairro(e.bairro_id).nome}</span></div>
    <div><div class="est-nivel"><span class="v" data-v="nivel"></span><span data-v="nivelrisco"></span></div></div>
    <div class="est-dados">
      <div><span>Chuva</span><b data-v="chuva"></b></div><div><span>Umidade do solo</span><b data-v="umid"></b></div>
      <div><span>Bateria</span><b data-v="bat"></b></div><div><span>Estado</span><b data-v="estado"></b></div>
      <div><span>Última leitura</span><b data-v="ts"></b></div><div><span>Sequência</span><b data-v="seq"></b></div>
    </div>
    <div class="est-spark"><div data-v="spark"></div><div class="rot"><span>24 h atrás</span><span>cota de alerta ${metros(e.cota_alerta_cm)}</span><span>agora</span></div></div>
  </article>`)}`);
  C.reguas = {};
  for (const e of C.territorio.estacoes) C.reguas[e.id] = criarRegua($(`#rg-${e.id}`), { cotaAlerta: e.cota_alerta_cm, cotaTransbordo: e.cota_transbordo_cm, compacta: true, titulo: `Régua da estação ${e.nome}` });
  atualizarEstacoes();
}
function atualizarEstacoes() {
  if (!$("#estacoes")) return;
  const online = C.estacoes.filter((e) => e.estado !== "offline").length;
  $("#ctx").textContent = `${online} de ${C.territorio.estacoes.length} estações transmitindo · cenário ${CENARIOS[C.cenario]?.rotulo?.toLowerCase() ?? "—"}`;
  for (const e of C.territorio.estacoes) {
    const card = $(`.est[data-id="${e.id}"]`); if (!card) continue;
    const st = C.estacoes.find((x) => x.id === e.id); const u = st?.ultima_leitura; if (!u) continue;
    const r = riscoDe(e.bairro_id);
    const v = (k) => card.querySelector(`[data-v="${k}"]`);
    v("nivel").innerHTML = `${(u.nivel_cm / 100).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}<small> m</small>`;
    v("nivelrisco").innerHTML = r ? String(etiquetaNivel(r.nivel)) : "";
    v("chuva").textContent = `${n1(u.chuva_mm_h)} mm/h`;
    v("umid").textContent = `${n1(u.umidade_solo_pct)}%`;
    const bat = Math.round(st.bateria_pct ?? u.bateria_pct);
    v("bat").innerHTML = `<span class="bateria" data-q="${bat < 20 ? 2 : bat < 40 ? 1 : 0}"><span class="bt"><i style="width:${bat}%"></i></span>${bat}%</span>`;
    const est = st.estado ?? "online";
    v("estado").innerHTML = `<span class="est-estado" data-e="${est}">${{ online: "online", bateria_baixa: "bateria baixa", offline: "sem sinal" }[est] ?? est}</span>`;
    v("ts").textContent = hora(u.ts);
    v("seq").textContent = `#${u.seq}`;
    v("spark").innerHTML = sparkline(C.series[e.id] ?? [], { w: 300, h: 44, cota: e.cota_alerta_cm, max: e.cota_transbordo_cm });
    C.reguas[e.id]?.atualizar(u.nivel_cm);
  }
  const log = $("#log");
  if (log) {
    log.innerHTML = `<div class="cab"><span>hora</span><span>estação</span><span>nível</span><span>chuva</span><span>solo</span><span>seq</span></div>` +
      C.log.slice(0, 24).map((l, i) => `<div class="${i < 4 ? "nova" : ""}"><span>${hora(l.ts)}</span><span>${esc(l.estacao_id)}</span><b>${n1(l.nivel_cm)} cm</b><span>${n1(l.chuva_mm_h)} mm/h</span><span>${n1(l.umidade_solo_pct)}%</span><span>#${l.seq}</span></div>`).join("");
  }
}

iniciar();
