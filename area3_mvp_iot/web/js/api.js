// Fachada única de dados do Margem (CONTRATOS §8).
// Na inicialização tenta GET /api/v1/health. Se responder, usa a API real (JWT + SSE em /stream).
// Se não responder (ex.: GitHub Pages ou API desligada), entra no MODO DEMONSTRAÇÃO (js/demo/),
// que roda um motor no navegador com os mesmos formatos do contrato.

const PREFIXO = (() => {
  const q = new URLSearchParams(location.search).get("api");
  const base = q || window.MARGEM_API || "";
  return `${base.replace(/\/$/, "")}/api/v1`;
})();

const EVENTOS_SSE = ["leitura", "risco", "alerta", "ocorrencia", "checkin", "cenario"];
const MAX_EXTRAPOLA_MS = 5000; // sem notícia do servidor, o relógio simulado para de andar depois de 5 s

export class ErroApi extends Error {
  constructor(codigo, mensagem, status) { super(mensagem); this.codigo = codigo; this.status = status; }
}

const espera = (ms) => new Promise((r) => setTimeout(r, ms));

function criarApi(superficie) {
  const chaveSessao = `margem:sessao:${superficie}`;
  const ouvintes = new Set();
  let modo = null; // "real" | "demo"
  let motor = null;
  let offline = false;
  let fonte = null;
  let reconexao = null;
  // Relógio da API: com a simulação ligada, ele anda acelerado (ex.: 10 min simulados a cada 2 s).
  // O front acompanha para "há X min", espera da fila e filtros do dashboard ficarem na mesma linha do tempo.
  const relogio = { base: null, em: 0, taxa: 1 };
  const sincronizar = (iso, taxa) => { if (iso) { relogio.base = new Date(iso).getTime(); relogio.em = Date.now(); relogio.taxa = Number(taxa) || 1; } };
  const agoraReal = () => {
    if (relogio.base == null) return new Date();
    const dt = Date.now() - relogio.em;
    return new Date(relogio.base + (relogio.taxa > 1 ? Math.min(dt, MAX_EXTRAPOLA_MS) : dt) * relogio.taxa);
  };

  const sessao = () => { try { return JSON.parse(localStorage.getItem(chaveSessao)) ?? null; } catch { return null; } };
  const salvarSessao = (s) => (s ? localStorage.setItem(chaveSessao, JSON.stringify(s)) : localStorage.removeItem(chaveSessao));
  const emitir = (ev) => ouvintes.forEach((fn) => { try { fn(ev); } catch (e) { console.error(e); } });

  // ---------- Caminho real ----------
  async function req(metodo, rota, corpo, { publico = false, cache = null } = {}) {
    const h = { Accept: "application/json" };
    if (corpo !== undefined) h["Content-Type"] = "application/json";
    const s = sessao();
    if (s?.token && !publico) h.Authorization = `Bearer ${s.token}`;
    let resp;
    try {
      resp = await fetch(PREFIXO + rota, { method: metodo, headers: h, body: corpo === undefined ? undefined : JSON.stringify(corpo) });
    } catch (e) {
      // Sem rede: devolve o último estado salvo, se houver
      if (cache) {
        const c = lerCache(cache);
        if (c) { marcarOffline(true); return c.dados; }
      }
      marcarOffline(true);
      throw new ErroApi("sem_conexao", "Sem conexão com o servidor. Confira a internet e tente de novo.", 0);
    }
    marcarOffline(false);
    const texto = await resp.text();
    const dados = texto ? JSON.parse(texto) : null;
    if (!resp.ok) {
      if (resp.status === 401 && !publico) salvarSessao(null);
      const e = dados?.erro ?? {};
      throw new ErroApi(e.codigo ?? `http_${resp.status}`, e.mensagem ?? "Algo deu errado no servidor.", resp.status);
    }
    if (cache) gravarCache(cache, dados);
    return dados;
  }

  // SSE: eventos públicos para todos; logado, pede antes um ticket de uso único (o JWT nunca vai na URL)
  // para receber também ocorrências/check-ins (console) ou os próprios relatos (morador).
  async function abrirStream() {
    if (!("EventSource" in window)) return;
    clearTimeout(reconexao);
    fonte?.close(); fonte = null;
    let q = "";
    if (sessao()?.token) {
      try { const t = await req("POST", "/stream/ticket"); q = `?ticket=${encodeURIComponent(t.ticket)}`; } catch { /* segue só com os eventos públicos */ }
    }
    const f = new EventSource(`${PREFIXO}/stream${q}`);
    fonte = f;
    const ler = (fn) => (ev) => { try { fn(JSON.parse(ev.data)); } catch { /* evento malformado */ } };
    for (const tipo of EVENTOS_SSE) f.addEventListener(tipo, ler((dados) => emitir({ tipo, dados })));
    f.addEventListener("relogio", ler((d) => sincronizar(d.relogio, d.taxa)));
    f.addEventListener("inicial", ler((d) => sincronizar(d.relogio, d.taxa)));
    f.onopen = () => marcarOffline(false);
    f.onerror = () => {
      marcarOffline(!navigator.onLine);
      // o ticket é de uso único: em vez da reconexão automática do EventSource, reabre com um ticket novo
      if (fonte === f) { f.close(); fonte = null; reconexao = setTimeout(abrirStream, 3000); }
    };
  }

  // ---------- Cache do último estado (uso offline) ----------
  function gravarCache(k, dados) { try { localStorage.setItem(`margem:cache:${k}`, JSON.stringify({ em: Date.now(), dados })); } catch { /* cheio */ } }
  function lerCache(k) { try { return JSON.parse(localStorage.getItem(`margem:cache:${k}`)); } catch { return null; } }
  function marcarOffline(v) { if (v !== offline) { offline = v; emitir({ tipo: "conexao", dados: { offline: v } }); } }

  // ---------- Demo: chama o motor com latência curta e erros no mesmo formato ----------
  async function demo(fn, ms = 60) {
    await espera(ms);
    try { return structuredClone(fn()); }
    catch (e) { throw new ErroApi(e.codigo ?? "erro", e.message, e.status ?? 400); }
  }
  const eu = () => {
    const s = sessao();
    if (!s) throw new ErroApi("nao_autenticado", "Entre na sua conta.", 401);
    return s.usuario;
  };

  const api = {
    get modo() { return modo; },
    get offline() { return offline; },
    superficie,

    async iniciar() {
      if (modo) return modo;
      try {
        const ctl = new AbortController();
        const t = setTimeout(() => ctl.abort(), 1800);
        const r = await fetch(`${PREFIXO}/health`, { signal: ctl.signal, cache: "no-store" });
        clearTimeout(t);
        const j = r.ok ? await r.json().catch(() => null) : null;
        if (!r.ok || !j) throw new Error("sem api");
        modo = "real";
        sincronizar(j.relogio, j.taxa_relogio);
        abrirStream();
      } catch {
        modo = "demo";
        const m = await import("./demo/motor.js");
        motor = m.motor;
        motor.iniciar();
        motor.on(emitir);
      }
      addEventListener("online", () => marcarOffline(false));
      addEventListener("offline", () => marcarOffline(true));
      if (!navigator.onLine) marcarOffline(true);
      return modo;
    },

    on(fn) { ouvintes.add(fn); return () => ouvintes.delete(fn); },
    agora() { return motor ? motor.agora() : agoraReal(); },
    usuario() { return sessao()?.usuario ?? null; },
    sair() { salvarSessao(null); if (modo === "real") abrirStream(); },
    idadeCache(k) { const c = lerCache(k); return c ? c.em : null; },

    // Auth
    async login(email, senha) {
      const r = modo === "demo" ? await demo(() => motor.login(email, senha), 350) : await req("POST", "/auth/login", { email, senha }, { publico: true });
      salvarSessao(r); if (modo === "real") abrirStream(); return r;
    },
    async cadastro(dados) {
      const r = modo === "demo" ? await demo(() => motor.cadastro(dados), 450) : await req("POST", "/auth/cadastro", dados, { publico: true });
      if (r?.token) { salvarSessao(r); if (modo === "real") abrirStream(); }
      else if (r) salvarSessao(await api.login(dados.email, dados.senha));
      return sessao();
    },
    async eu() {
      if (modo === "demo") return demo(() => { const u = motor.usuarioDoToken(sessao()?.token); if (!u) throw Object.assign(new Error("Sessão expirada."), { codigo: "nao_autenticado", status: 401 }); return u; });
      return req("GET", "/auth/eu");
    },

    // Território, estações e risco
    territorio: () => (modo === "demo" ? demo(() => motor.territorio(), 0) : req("GET", "/territorio", undefined, { publico: true, cache: "territorio" })),
    estacoes: () => (modo === "demo" ? demo(() => motor.estacoes()) : req("GET", "/iot/estacoes", undefined, { cache: "estacoes" })),
    leituras: (estacao_id, horas = 24) => (modo === "demo" ? demo(() => motor.leituras(estacao_id, horas)) : req("GET", `/iot/leituras?estacao_id=${encodeURIComponent(estacao_id)}&horas=${horas}`, undefined, { cache: `leituras:${estacao_id}` })),
    riscoAtual: () => (modo === "demo" ? demo(() => motor.riscoAtual(), 20) : req("GET", "/risco/atual", undefined, { publico: true, cache: "risco" })),

    // Ocorrências
    criarOcorrencia: (body) => (modo === "demo" ? demo(() => motor.criarOcorrencia(body, eu()), 500) : req("POST", "/ocorrencias", body)),
    ocorrencias: () => (modo === "demo" ? demo(() => motor.ocorrencias(eu())) : req("GET", "/ocorrencias", undefined, { cache: `ocorrencias:${superficie}` })),
    atualizarOcorrencia: (id, status) => (modo === "demo" ? demo(() => motor.atualizarOcorrencia(id, { status }), 150) : req("PATCH", `/ocorrencias/${encodeURIComponent(id)}`, { status })),

    // Check-ins
    checkin: (status, obs) => (modo === "demo" ? demo(() => motor.checkin({ status, obs }, eu()), 300) : req("POST", "/checkins", { status, obs })),
    checkins: () => (modo === "demo" ? demo(() => motor.checkins()) : req("GET", "/checkins")),

    // Alertas
    alertas: (bairro_id) => (modo === "demo" ? demo(() => motor.alertas(bairro_id)) : req("GET", `/alertas${bairro_id ? `?bairro_id=${encodeURIComponent(bairro_id)}` : ""}`, undefined, { publico: true, cache: `alertas:${bairro_id ?? "todos"}` })),
    rascunhoAlerta: (bairro_id) => (modo === "demo" ? demo(() => motor.rascunhoAlerta({ bairro_id }), 700) : req("POST", "/alertas/rascunho", { bairro_id })),
    emitirAlerta: (body) => (modo === "demo" ? demo(() => motor.emitirAlerta(body, eu()), 300) : req("POST", "/alertas", body)),

    // Dashboard e simulação
    indicadores: (f = {}) => {
      if (modo === "demo") return demo(() => motor.indicadores(f), 120);
      const q = new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString();
      return req("GET", `/dashboard/indicadores${q ? `?${q}` : ""}`);
    },
    cenario: (cenario) => (modo === "demo" ? demo(() => motor.cenario(cenario), 120) : req("POST", "/simulacao/cenario", { cenario })),
    cenarioAtual: async () => {
      if (modo === "demo") return demo(() => motor.cenarioAtual(), 0);
      const c = await req("GET", "/simulacao/cenario", undefined, { publico: true });
      sincronizar(c?.relogio, c?.taxa);
      return c;
    },
    reiniciarDemo: () => motor?.reiniciar(),
  };
  return api;
}

export const apiPara = (superficie) => criarApi(superficie);
