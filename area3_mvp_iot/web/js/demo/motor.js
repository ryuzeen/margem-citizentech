// Motor do modo demonstração: roda inteiro no navegador quando a API não responde (ex.: GitHub Pages).
// Respeita os formatos de docs/CONTRATOS.md (§3, §4, §7, §8, §9). Tudo aqui é SIMULADO.
// - Relógio simulado acelerado: cada passo (3 s reais) = 5 min de rio.
// - Uma aba é a "líder" (Web Locks) e faz a simulação andar; as outras escutam pelo BroadcastChannel.
// - Persistência em localStorage, para o app do morador e o console conversarem em abas diferentes.
import { TERRITORIO } from "./territorio.js";
import { nivelPorCota, nivelPorProb, maiorNivel, indice, ROTULO } from "../niveis.js";
import { triar, calcularPrioridade, redigirAlerta } from "./triagem.js";

const CHAVE = "margem:demo:v3";
const PASSO_REAL_MS = 3000;
const PASSO_SIM_MS = 5 * 60 * 1000;
const PONTOS_SERIE = 288; // 24 h de 5 em 5 min
const FATOR_EST = { "EST-PANTANAL-01": 1.08, "EST-ITAIM-01": 0.95, "EST-ROMANO-01": 1.04, "EST-HELENA-01": 0.8 };
const CENARIO = {
  normal: { f: 0.04, chuva: [0, 1.5], umid: 48, alfa: 0.06 },
  chuva_forte: { f: 0.66, chuva: [25, 40], umid: 80, alfa: 0.075 },
  enchente: { f: 1.18, chuva: [62, 88], umid: 96, alfa: 0.075 },
  recuperacao: { f: 0.0, chuva: [0, 0.5], umid: 58, alfa: 0.035 },
};

// ---------- Aleatoriedade com semente ----------
function rngDe(seed) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
let rnd = rngDe(Date.now() % 100000);
const entre = (a, b, r = rnd) => a + (b - a) * r();
const escolha = (arr, r = rnd) => arr[Math.floor(r() * arr.length)];
const fuso = (d) => {
  // ISO com fuso -03:00 (São Paulo)
  const t = new Date(d.getTime() - 3 * 3600e3);
  return t.toISOString().slice(0, 19) + "-03:00";
};

const NOMES = ["Josefa", "Antônio", "Cícera", "Raimundo", "Francisca", "Edvaldo", "Luzia", "Marcos", "Rosângela", "Severino", "Aparecida", "Joelma",
  "Wellington", "Benedita", "Cleide", "Damião", "Ivone", "Reginaldo", "Sueli", "Valdir", "Neide", "Adriana", "Gilmar", "Terezinha"];
const SOBRE = ["S.", "R.", "O.", "L.", "A.", "M.", "F.", "P.", "C.", "B.", "N.", "G."];

const RELATOS = [
  "A água da rua já passou da calçada e está entrando no quintal",
  "Água entrando em casa pela porta da cozinha, já está no tornozelo",
  "Minha avó de 82 anos mora sozinha e a rua dela está alagada, não consigo chegar",
  "Rua toda alagada perto da ponte, carro parado no meio da água",
  "Muro do vizinho com rachadura grande depois da chuva, parece que vai cair",
  "Estamos ilhados no segundo andar, a água está subindo rápido, tem criança aqui",
  "Sem luz na rua inteira e tem fio caído perto da água",
  "Córrego transbordou e a água invadiu a sala, tenho um bebê de 6 meses",
  "Meu pai é acamado e a água está chegando no quarto, precisamos de ajuda para tirar ele",
  "Viela alagada, as pessoas estão passando com água na cintura",
  "Água entrando na casa da frente, moradora é cadeirante",
  "Bueiro estourou e a rua virou rio, não dá pra sair de carro",
];

// ---------- Estado ----------
let estado = null;
let ouvintes = new Set();
let canal = null;
let souLider = false;
let timer = null;
const idAba = Math.random().toString(36).slice(2, 8);

const agoraMs = () => Date.now() + (estado?.offsetMs ?? 0);
export const agora = () => new Date(agoraMs());
const estacaoDe = (id) => TERRITORIO.estacoes.find((e) => e.id === id);
const bairroDe = (id) => TERRITORIO.bairros.find((b) => b.id === id);

function ler() {
  try { const s = localStorage.getItem(CHAVE); return s ? JSON.parse(s) : null; } catch { return null; }
}
function gravar() {
  try { localStorage.setItem(CHAVE, JSON.stringify(estado)); } catch (e) {
    // Sem espaço: descarta o histórico mais antigo e tenta de novo.
    estado.ocorrencias = estado.ocorrencias.slice(0, 120);
    try { localStorage.setItem(CHAVE, JSON.stringify(estado)); } catch { /* segue só em memória */ }
  }
}
function recarregar() { const s = ler(); if (s) estado = s; }

function emitir(tipo, dados, { propagar = true } = {}) {
  for (const fn of ouvintes) { try { fn({ tipo, dados }); } catch (e) { console.error(e); } }
  if (propagar && canal) canal.postMessage({ de: idAba, tipo, dados });
}

// ---------- Hidrologia ----------
function semear() {
  const r = rngDe(20261105);
  const t0 = Date.now();
  const est = {};
  for (const e of TERRITORIO.estacoes) {
    const serie = [];
    let nivel = e.nivel_base_cm + 6;
    for (let i = PONTOS_SERIE - 1; i >= 0; i--) {
      const ts = t0 - i * PASSO_SIM_MS;
      // pancada de chuva fraca ~10 h atrás
      const h = i * 5 / 60;
      const chuva = h > 9 && h < 11 ? 6 + 4 * Math.sin((h - 9) * Math.PI / 2) : Math.max(0, r() - 0.93) * 4;
      const alvo = e.nivel_base_cm + (h > 6 && h < 11 ? 26 * FATOR_EST[e.id] : 0);
      nivel += (alvo - nivel) * 0.05 + (r() - 0.5) * 1.4;
      serie.push({ ts: fuso(new Date(ts)), nivel_cm: +nivel.toFixed(1), chuva_mm_h: +chuva.toFixed(1), umidade_solo_pct: +(46 + (h > 6 && h < 14 ? 12 : 0) + r() * 3).toFixed(1) });
    }
    const ult = serie.at(-1);
    est[e.id] = {
      nivel_cm: ult.nivel_cm, chuva_mm_h: ult.chuva_mm_h, umidade_solo_pct: ult.umidade_solo_pct,
      bateria_pct: { "EST-PANTANAL-01": 88, "EST-ITAIM-01": 71, "EST-ROMANO-01": 93, "EST-HELENA-01": 34 }[e.id],
      seq: 1400 + Math.floor(r() * 200), firmware: "1.0.0", serie,
    };
  }
  const usuarios = [
    { id: 1, email: "maria@demo.margem.app", senha: "Margem@2026", nome: "Maria Aparecida Souza", papel: "cidadao", telefone: "11987654321",
      bairro_id: "jardim-pantanal", vulnerabilidades: [], contato_emergencia: "Filha — (11) 91234-5678", consentimento_lgpd_em: fuso(new Date(t0 - 40 * 864e5)), criado_em: fuso(new Date(t0 - 40 * 864e5)) },
    { id: 2, email: "operador@demo.margem.app", senha: "DefesaCivil@2026", nome: "Operador COMDEC Itaim Paulista", papel: "defesa_civil", telefone: "1133960000",
      bairro_id: null, vulnerabilidades: [], contato_emergencia: null, consentimento_lgpd_em: null, criado_em: fuso(new Date(t0 - 90 * 864e5)) },
  ];
  estado = {
    versao: 3, offsetMs: 0, cenario: "normal", cenario_desde: fuso(new Date(t0)), seqOc: 117, seqAl: 41, seqCk: 300,
    estacoes: est, usuarios, ocorrencias: [], checkins: [], alertas: [], simulados: { oc: 0, ck: 0 },
  };
  // Fila inicial (dia comum): poucos relatos abertos e alguns resolvidos
  const iniciais = [
    ["jardim-romano", "Bueiro entupido na rua e a água da chuva não escoa, já está na calçada", 95, "aberta"],
    ["vila-itaim", "Sem luz na rua desde a chuva de ontem, tem fio baixo perto da viela", 140, "aberta"],
    ["jardim-pantanal", "Muro do terreno ao lado com rachadura que aumentou depois da chuva", 62, "em_atendimento"],
    ["jardim-helena", "Rua alagada na esquina da escola, as crianças estão passando pela água", 38, "aberta"],
    ["jardim-pantanal", "Água entrou no quintal ontem à noite, já baixou, mas ficou muita lama", 460, "resolvida"],
  ];
  for (const [b, txt, min, st] of iniciais) {
    const oc = novaOcorrencia({ texto: txt, bairro_id: b }, { nome: `${escolha(NOMES, r)} ${escolha(SOBRE, r)}`, vulnerabilidades: [] }, "app", t0 - min * 60e3);
    oc.status = st;
    if (st !== "aberta") oc.atendido_em = fuso(new Date(t0 - (min - 24) * 60e3));
    if (st === "resolvida") oc.resolvido_em = fuso(new Date(t0 - (min - 140) * 60e3));
    estado.ocorrencias.push(oc);
  }
  for (let i = 0; i < 5; i++) {
    const b = TERRITORIO.bairros[i % 4].id;
    estado.checkins.push(novoCheckin({ status: "seguro", obs: "" }, morador(r, b), t0 - (30 + i * 47) * 60e3));
  }
}

function morador(r, bairro_id) {
  const vul = r() < 0.35 ? [escolha(["idoso", "idoso", "pcd", "crianca", "gestante", "acamado"], r)] : [];
  return { id: 1000 + Math.floor(r() * 9000), nome: `${escolha(NOMES, r)} ${escolha(SOBRE, r)}`, telefone: `119${Math.floor(10000000 + r() * 89999999)}`, bairro_id, vulnerabilidades: vul };
}

function variacao(serie, passos) {
  if (serie.length <= passos) return 0;
  return serie.at(-1).nivel_cm - serie.at(-1 - passos).nivel_cm;
}
function chuvaAcum(serie, passos) {
  return serie.slice(-passos).reduce((s, p) => s + p.chuva_mm_h * (5 / 60), 0);
}

/** Substituto do MLP de risco 2h (área 1). Mesmas entradas que as features de leituras_hora. */
export function probabilidade(e, s) {
  const pct = s.nivel_cm / e.cota_alerta_cm;
  const v1h = variacao(s.serie, 12);
  const c1h = chuvaAcum(s.serie, 12);
  const z = -6.0 + 4.4 * pct + 0.022 * v1h + 0.008 * c1h + 0.006 * s.chuva_mm_h + 0.012 * (s.umidade_solo_pct - 60);
  return 1 / (1 + Math.exp(-z));
}

function riscoBairro(b) {
  const e = estacaoDe(b.estacao_id);
  const s = estado.estacoes[e.id];
  const prob = probabilidade(e, s);
  const v15 = variacao(s.serie, 3);
  const tendencia = v15 > 2 ? "subindo" : v15 < -2 ? "descendo" : "estavel";
  const ult = s.serie.at(-1);
  return {
    bairro_id: b.id,
    nivel: maiorNivel(nivelPorCota(s.nivel_cm, e.cota_alerta_cm, e.cota_transbordo_cm), nivelPorProb(prob)),
    nivel_por_cota: nivelPorCota(s.nivel_cm, e.cota_alerta_cm, e.cota_transbordo_cm),
    prob: +prob.toFixed(3), tendencia, atualizado_em: ult.ts,
    estacao_id: e.id, nivel_cm: s.nivel_cm, cota_alerta_cm: e.cota_alerta_cm, cota_transbordo_cm: e.cota_transbordo_cm,
    pct_cota_alerta: +(s.nivel_cm / e.cota_alerta_cm).toFixed(3), variacao_1h_cm: +variacao(s.serie, 12).toFixed(1), chuva_mm_h: s.chuva_mm_h,
  };
}

function passo() {
  recarregar();
  estado.offsetMs += PASSO_SIM_MS - PASSO_REAL_MS;
  const c = CENARIO[estado.cenario] ?? CENARIO.normal;
  const ts = fuso(agora());
  const antes = Object.fromEntries(TERRITORIO.bairros.map((b) => [b.id, riscoBairro(b).nivel]));
  const leituras = [];
  for (const e of TERRITORIO.estacoes) {
    const s = estado.estacoes[e.id];
    const alvo = e.nivel_base_cm + (e.cota_transbordo_cm - e.nivel_base_cm) * c.f * FATOR_EST[e.id];
    const subindo = alvo > s.nivel_cm;
    const alfa = subindo ? c.alfa : (estado.cenario === "recuperacao" ? 0.035 : 0.05);
    s.nivel_cm = Math.min(e.altura_instalacao_cm - 20, Math.max(0, s.nivel_cm + (alvo - s.nivel_cm) * alfa + (rnd() - 0.5) * 1.6));
    const chuvaAlvo = entre(c.chuva[0], c.chuva[1]);
    s.chuva_mm_h = Math.max(0, s.chuva_mm_h + (chuvaAlvo - s.chuva_mm_h) * 0.45);
    s.umidade_solo_pct = Math.min(100, s.umidade_solo_pct + (c.umid - s.umidade_solo_pct) * 0.08);
    s.bateria_pct = Math.max(5, +(s.bateria_pct - 0.03).toFixed(2));
    s.seq += 1;
    const leitura = { estacao_id: e.id, ts, seq: s.seq, nivel_cm: +s.nivel_cm.toFixed(1), chuva_mm_h: +s.chuva_mm_h.toFixed(1),
      umidade_solo_pct: +s.umidade_solo_pct.toFixed(1), bateria_pct: Math.round(s.bateria_pct), firmware: s.firmware };
    s.serie.push({ ts, nivel_cm: leitura.nivel_cm, chuva_mm_h: leitura.chuva_mm_h, umidade_solo_pct: leitura.umidade_solo_pct });
    if (s.serie.length > PONTOS_SERIE) s.serie.splice(0, s.serie.length - PONTOS_SERIE);
    leituras.push(leitura);
  }
  const risco = TERRITORIO.bairros.map(riscoBairro);
  // Moradores simulados relatam e fazem check-in quando o bairro está em Alerta ou acima
  const novas = [], novosCk = [];
  for (const rb of risco) {
    if (indice(rb.nivel) < 2) continue;
    if (estado.simulados.oc < 9 && rnd() < 0.1) {
      const m = morador(rnd, rb.bairro_id);
      const oc = novaOcorrencia({ texto: escolha(RELATOS), bairro_id: rb.bairro_id }, m, "simulado", agoraMs(), rb.nivel);
      estado.ocorrencias.unshift(oc); estado.simulados.oc++; novas.push(oc);
    }
    if (estado.simulados.ck < 18 && rnd() < 0.16) {
      const m = morador(rnd, rb.bairro_id);
      const st = rnd() < (rb.nivel === "alerta_maximo" ? 0.4 : 0.2) ? "preciso_ajuda" : "seguro";
      const ck = novoCheckin({ status: st, obs: st === "preciso_ajuda" ? escolha(["Água subindo dentro de casa", "Não consigo sair sozinha", "Estou com duas crianças"]) : "" }, m, agoraMs());
      estado.checkins.unshift(ck); estado.simulados.ck++; novosCk.push(ck);
    }
  }
  estado.checkins = estado.checkins.slice(0, 200);
  gravar();
  for (const l of leituras) emitir("leitura", l);
  emitir("risco", risco);
  for (const oc of novas) emitir("ocorrencia", comPrioridade(oc));
  for (const ck of novosCk) emitir("checkin", ck);
  for (const rb of risco) if (antes[rb.bairro_id] !== rb.nivel) emitir("nivel_mudou", { bairro_id: rb.bairro_id, de: antes[rb.bairro_id], para: rb.nivel });
}

// ---------- Entidades ----------
function abrigoDe(bairro_id) {
  return TERRITORIO.abrigos.find((a) => a.bairro_id === bairro_id) ?? null;
}

function novaOcorrencia({ texto, bairro_id, lat, lng }, usuario, origem, ms, nivelBairro) {
  const b = bairroDe(bairro_id) ?? TERRITORIO.bairros[0];
  const nv = nivelBairro ?? (estado?.estacoes ? riscoBairro(b).nivel : "observacao");
  const triagem = triar(texto, { nivelBairro: nv, vulnPerfil: usuario?.vulnerabilidades ?? [], nomeBairro: b.nome, abrigo: abrigoDe(b.id) });
  const id = `OC-${String(++estado.seqOc).padStart(6, "0")}`;
  const ts = fuso(new Date(ms));
  return {
    id, criado_em: ts, atualizado_em: ts, status: "aberta", bairro_id: b.id, texto, lat: lat ?? null, lng: lng ?? null,
    usuario_id: usuario?.id ?? null, usuario_nome: usuario?.nome ?? null, origem, atendido_em: null, resolvido_em: null,
    nivel_bairro_no_relato: nv, triagem,
  };
}

function comPrioridade(oc) {
  if (oc.status !== "aberta") return oc;
  const espera = (agoraMs() - new Date(oc.criado_em).getTime()) / 60000;
  const b = bairroDe(oc.bairro_id);
  const p = calcularPrioridade(oc.triagem.gravidade, oc.triagem.vulneraveis.length, riscoBairro(b).nivel, espera);
  return { ...oc, triagem: { ...oc.triagem, prioridade: p.total } };
}

function novoCheckin({ status, obs }, usuario, ms) {
  return {
    id: ++estado.seqCk, usuario_id: usuario.id, nome: usuario.nome, telefone_mascarado: mascarar(usuario.telefone),
    bairro_id: usuario.bairro_id, status, obs: obs || "", vulnerabilidades: usuario.vulnerabilidades ?? [], criado_em: fuso(new Date(ms)),
  };
}
function mascarar(t) {
  const d = String(t ?? "").replace(/\D/g, "");
  return d.length >= 8 ? `(${d.slice(0, 2)}) •••••-${d.slice(-4)}` : "não informado";
}

function erro(codigo, mensagem, status = 400) {
  const e = new Error(mensagem); e.codigo = codigo; e.status = status; return e;
}
function publico(u) { if (!u) return null; const { senha, ...resto } = u; return resto; }

// ---------- Histórico simulado (365 dias, como o da Área 2) para o dashboard: determinístico ----------
let _hist = null;
function historico() {
  if (_hist) return _hist;
  const r = rngDe(9090);
  const fim = Date.now();
  const ocorr = [], eventos = [], maxDia = {};
  const cats = ["agua_na_residencia", "via_alagada", "pessoa_ilhada", "risco_estrutural", "falta_energia", "outro"];
  const pesoCat = [0.34, 0.3, 0.06, 0.1, 0.12, 0.08];
  // ~13 dias de evento a cada 90 dias (o mesmo padrão dos 90 dias mais recentes, repetido ao longo do ano)
  const base = [4, 11, 12, 23, 31, 38, 39, 52, 60, 67, 74, 81, 86];
  const diasEvento = new Set([0, 90, 180, 270].flatMap((o) => base.map((d) => d + o)));
  for (let d = 365; d >= 1; d--) {
    const dia = fim - d * 864e5;
    const evento = diasEvento.has(d);
    for (const e of TERRITORIO.estacoes) {
      const pico = evento ? e.cota_alerta_cm * entre(0.85, 1.38, r) * (FATOR_EST[e.id] * 0.5 + 0.5) : e.nivel_base_cm + entre(5, 60, r);
      (maxDia[e.id] ??= []).push({ ts: fuso(new Date(dia)), nivel_cm: +Math.min(e.altura_instalacao_cm - 20, pico).toFixed(1) });
      if (evento && pico >= e.cota_transbordo_cm) {
        // melhora ao longo do tempo (modelo novo entrou há ~45 dias)
        const modelo = d < 45 ? entre(78, 118, r) : entre(42, 75, r);
        eventos.push({ ts: fuso(new Date(dia)), bairro_id: e.bairro_id, estacao_id: e.id, modelo_min: Math.round(modelo), cota_min: Math.round(entre(12, 34, r)) });
      }
    }
    const n = evento ? Math.round(entre(9, 26, r)) : Math.round(entre(0, 2.4, r));
    for (let i = 0; i < n; i++) {
      let x = r(), ci = 0; while (x > pesoCat[ci] && ci < 5) { x -= pesoCat[ci]; ci++; }
      const cat = cats[ci];
      const grav = Math.max(1, Math.min(5, Math.round({ pessoa_ilhada: 4.6, risco_estrutural: 3.8, agua_na_residencia: 3.1, falta_energia: 2, via_alagada: 2, outro: 1.3 }[cat] + entre(-0.8, 0.8, r))));
      const criado = dia + entre(0, 864e5, r);
      const espera = Math.max(4, (d < 45 ? 17 : 29) + (5 - grav) * 4 + entre(-10, 18, r));
      ocorr.push({ bairro_id: escolha(TERRITORIO.bairros, r).id, categoria: cat, gravidade: grav, status: "resolvida", criado_em: criado, atendido_min: espera });
    }
  }
  _hist = { ocorr, eventos, maxDia };
  return _hist;
}

// Moradores cadastrados (agregado simulado) por bairro, para o indicador 5
const CADASTRO = {
  "jardim-pantanal": { total: 612, vulneraveis: { idoso: 71, pcd: 29, crianca: 38, gestante: 9, acamado: 11 } },
  "vila-itaim": { total: 388, vulneraveis: { idoso: 44, pcd: 17, crianca: 26, gestante: 6, acamado: 5 } },
  "jardim-romano": { total: 455, vulneraveis: { idoso: 52, pcd: 21, crianca: 31, gestante: 7, acamado: 9 } },
  "jardim-helena": { total: 341, vulneraveis: { idoso: 46, pcd: 13, crianca: 19, gestante: 4, acamado: 6 } },
};

export const FORMULAS = {
  nivel_vs_cota: { titulo: "Nível vs cota", formula: "% da cota = nível atual (cm) ÷ cota de alerta (cm)", dax: "Pct Cota = DIVIDE(MAX(fato_leitura_hora[nivel_cm]), MAX(dim_estacao[cota_alerta_cm]))" },
  risco_bairro: { titulo: "Risco previsto por bairro", formula: "prob = saída do modelo de risco para as próximas 2 h; nível = maior entre a regra por cota e a regra por probabilidade", dax: "Prob 2h = CALCULATE(MAX(risco_bairro[prob]), LASTDATE(risco_bairro[hora]))" },
  ocorrencias: { titulo: "Ocorrências", formula: "contagem de ocorrências por categoria × gravidade × status no período", dax: "Ocorrências = COUNTROWS(fato_ocorrencia)" },
  tempo_atendimento: { titulo: "Tempo até atendimento", formula: "média(atendido_em − criado_em) das ocorrências atendidas; % ≤ 30 min = atendidas em até 30 min ÷ atendidas", dax: "Tempo Médio (min) = AVERAGEX(FILTER(fato_ocorrencia, NOT ISBLANK([atendido_em])), DATEDIFF([criado_em], [atendido_em], MINUTE))" },
  vulneraveis: { titulo: "Vulneráveis em área de risco", formula: "cadastrados com vulnerabilidade em bairros com nível ≥ Alerta; % check-in = com check-in nas últimas 6 h ÷ total", dax: "Vuln. em Risco = CALCULATE(SUM(dim_bairro[vulneraveis]), dim_bairro[nivel_idx] >= 2)" },
  antecedencia: { titulo: "Antecedência do alerta", formula: "minutos entre o primeiro alerta e o transbordo; modelo (prob ≥ 0,60) × regra só por cota", dax: "Antecedência Modelo = AVERAGEX(fato_alerta, DATEDIFF([emitido_em], [transbordo_em], MINUTE))" },
};

function calcularIndicadores({ bairro_id, de, ate, estacao_id } = {}) {
  const h = historico();
  const fim = ate ? new Date(ate).getTime() : agoraMs();
  const ini = de ? new Date(de).getTime() : fim - 30 * 864e5;
  const dias = (fim - ini) / 864e5;
  const filtraB = (x) => !bairro_id || x.bairro_id === bairro_id;
  const filtraBairro = (b) => !bairro_id || b.id === bairro_id;
  const ests = TERRITORIO.estacoes.filter((e) => (!estacao_id || e.id === estacao_id) && (!bairro_id || e.bairro_id === bairro_id));

  // 1. nível vs cota
  const nivel_vs_cota = ests.map((e) => {
    const s = estado.estacoes[e.id];
    const serie = dias <= 1.01
      ? s.serie.filter((p) => new Date(p.ts).getTime() >= ini).map((p) => ({ ts: p.ts, nivel_cm: p.nivel_cm }))
      : h.maxDia[e.id].filter((p) => new Date(p.ts).getTime() >= Date.now() - dias * 864e5).concat([{ ts: s.serie.at(-1).ts, nivel_cm: Math.max(...s.serie.slice(-288).map((p) => p.nivel_cm)) }]);
    return { estacao_id: e.id, nome: e.nome, cota_alerta_cm: e.cota_alerta_cm, cota_transbordo_cm: e.cota_transbordo_cm,
      nivel_atual_cm: s.nivel_cm, pct_cota_atual: +(s.nivel_cm / e.cota_alerta_cm).toFixed(3), agregacao: dias <= 1.01 ? "5min" : "max_diario", serie };
  });

  // 2. risco por bairro
  const risco_bairro = TERRITORIO.bairros.filter(filtraBairro).map((b) => { const r = riscoBairro(b); return { bairro_id: b.id, nome: b.nome, nivel: r.nivel, prob: r.prob, tendencia: r.tendencia }; })
    .sort((a, b) => b.prob - a.prob);

  // 3. ocorrências (histórico + vivas)
  const histOc = h.ocorr.filter((o) => o.criado_em >= Date.now() - dias * 864e5 && filtraB(o));
  const vivas = estado.ocorrencias.filter((o) => new Date(o.criado_em).getTime() >= ini && filtraB(o));
  const todas = [
    ...histOc.map((o) => ({ categoria: o.categoria, gravidade: o.gravidade, status: o.status, espera: o.atendido_min })),
    ...vivas.map((o) => ({ categoria: o.triagem.categoria, gravidade: o.triagem.gravidade, status: o.status,
      espera: o.atendido_em ? (new Date(o.atendido_em) - new Date(o.criado_em)) / 60000 : null })),
  ];
  const cats = ["agua_na_residencia", "via_alagada", "pessoa_ilhada", "risco_estrutural", "falta_energia", "outro"];
  const por_categoria = cats.map((c) => {
    const l = todas.filter((o) => o.categoria === c);
    const g = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 }, st = { aberta: 0, em_atendimento: 0, resolvida: 0 };
    l.forEach((o) => { g[o.gravidade]++; st[o.status]++; });
    return { categoria: c, total: l.length, por_gravidade: g, por_status: st };
  });
  const por_status = { aberta: 0, em_atendimento: 0, resolvida: 0 };
  todas.forEach((o) => por_status[o.status]++);

  // 4. tempo até atendimento
  const atendidas = todas.filter((o) => o.espera != null);
  const medio = atendidas.length ? atendidas.reduce((s, o) => s + o.espera, 0) / atendidas.length : 0;
  const ate30 = atendidas.length ? atendidas.filter((o) => o.espera <= 30).length / atendidas.length : 0;
  // semanas até ~6 meses; em períodos maiores, blocos de 30 dias (igual à API)
  const semanas = [];
  const agrupamento = dias <= 182 ? "semana" : "mes";
  const passoDias = agrupamento === "semana" ? 7 : 30;
  const nSem = Math.max(1, Math.ceil(dias / passoDias - 0.01));
  for (let i = nSem - 1; i >= 0; i--) {
    const a = Date.now() - (i + 1) * passoDias * 864e5, b = Date.now() - i * passoDias * 864e5;
    const l = histOc.filter((o) => o.criado_em >= a && o.criado_em < b);
    semanas.push({ inicio: fuso(new Date(a)), medio_min: l.length ? +(l.reduce((s, o) => s + o.atendido_min, 0) / l.length).toFixed(1) : null, total: l.length });
  }

  // 5. vulneráveis em área de risco
  const riscoAtual = Object.fromEntries(TERRITORIO.bairros.map((b) => [b.id, riscoBairro(b).nivel]));
  const emRisco = TERRITORIO.bairros.filter((b) => filtraBairro(b) && indice(riscoAtual[b.id]) >= 2);
  const tot = (b) => Object.values(CADASTRO[b.id].vulneraveis).reduce((s, n) => s + n, 0);
  const em_area_risco = emRisco.reduce((s, b) => s + tot(b), 0);
  const seisH = agoraMs() - 6 * 3600e3;
  const comCk = estado.checkins.filter((c) => new Date(c.criado_em).getTime() >= seisH && c.vulnerabilidades?.length && emRisco.some((b) => b.id === c.bairro_id));
  const fatorCk = Math.min(0.62, comCk.length * 0.045); // extrapola a amostra de check-ins para a base cadastrada
  const por_tipo = {};
  for (const b of TERRITORIO.bairros.filter(filtraBairro)) for (const [k, n] of Object.entries(CADASTRO[b.id].vulneraveis)) por_tipo[k] = (por_tipo[k] ?? 0) + n;

  // 6. antecedência
  const ev = h.eventos.filter((x) => new Date(x.ts).getTime() >= Date.now() - dias * 864e5 && filtraB(x) && (!estacao_id || x.estacao_id === estacao_id));
  const media = (k) => (ev.length ? ev.reduce((s, x) => s + x[k], 0) / ev.length : null);

  const abertas = estado.ocorrencias.filter((o) => o.status === "aberta" && filtraB(o)).length;
  return {
    gerado_em: fuso(agora()), filtros: { bairro_id: bairro_id ?? null, estacao_id: estacao_id ?? null, de: fuso(new Date(ini)), ate: fuso(new Date(fim)) },
    kpis: {
      ocorrencias_periodo: todas.length, ocorrencias_abertas: abertas, tempo_medio_atendimento_min: +medio.toFixed(1), pct_atendidas_30min: +ate30.toFixed(3),
      vulneraveis_area_risco: em_area_risco, pct_vulneraveis_checkin: em_area_risco ? +fatorCk.toFixed(3) : 0,
      antecedencia_modelo_min: media("modelo_min") && Math.round(media("modelo_min")), antecedencia_cota_min: media("cota_min") && Math.round(media("cota_min")),
      bairros_em_alerta: emRisco.length,
    },
    nivel_vs_cota, risco_bairro,
    ocorrencias: { por_categoria, por_status, total: todas.length },
    tempo_atendimento: { medio_min: +medio.toFixed(1), pct_ate_30min: +ate30.toFixed(3), agrupamento, por_semana: semanas },
    vulneraveis: { em_area_risco, com_checkin: Math.round(em_area_risco * fatorCk), pct_checkin: em_area_risco ? +fatorCk.toFixed(3) : 0, por_tipo, bairros_em_risco: emRisco.map((b) => b.id) },
    antecedencia: { modelo_min: media("modelo_min") && Math.round(media("modelo_min")), cota_min: media("cota_min") && Math.round(media("cota_min")),
      ganho_min: ev.length ? Math.round(media("modelo_min")) - Math.round(media("cota_min")) : null, eventos: ev },
    formulas: FORMULAS,
  };
}

// ---------- API pública do motor (mesmos métodos do §8) ----------
export const motor = {
  iniciar() {
    recarregar();
    if (!estado || estado.versao !== 3) { semear(); gravar(); }
    if ("BroadcastChannel" in window) {
      canal = new BroadcastChannel("margem-demo");
      canal.onmessage = (ev) => {
        const m = ev.data; if (!m || m.de === idAba) return;
        recarregar();
        emitir(m.tipo, m.dados, { propagar: false });
      };
    }
    addEventListener("storage", (ev) => { if (ev.key === CHAVE) recarregar(); });
    const virarLider = () => { souLider = true; clearInterval(timer); timer = setInterval(passo, PASSO_REAL_MS); };
    // A aba visível assume a simulação (abas em segundo plano têm o timer estrangulado pelo navegador).
    const pedirLider = (roubar) => {
      navigator.locks.request("margem-demo-lider", { steal: roubar }, () => new Promise(() => virarLider()))
        .catch(() => { souLider = false; clearInterval(timer); pedirLider(false); });
    };
    if (navigator.locks?.request) {
      pedirLider(document.visibilityState === "visible");
      document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && !souLider) pedirLider(true); });
    } else virarLider();
  },
  on(fn) { ouvintes.add(fn); return () => ouvintes.delete(fn); },
  agora,
  lider: () => souLider,
  reiniciar() { localStorage.removeItem(CHAVE); semear(); gravar(); emitir("reinicio", {}); },

  login(email, senha) {
    recarregar();
    const u = estado.usuarios.find((x) => x.email.toLowerCase() === String(email).trim().toLowerCase());
    if (!u || u.senha !== senha) throw erro("credenciais_invalidas", "E-mail ou senha não conferem.", 401);
    return { token: `demo.${u.id}.${Date.now().toString(36)}`, usuario: publico(u) };
  },
  cadastro(d) {
    recarregar();
    if (!d.consentimento_lgpd) throw erro("consentimento_obrigatorio", "Para criar a conta é preciso aceitar o uso dos dados.");
    if (!d.email || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(d.email)) throw erro("email_invalido", "Confira o e-mail.");
    if (!d.senha || d.senha.length < 8) throw erro("senha_fraca", "A senha precisa ter pelo menos 8 caracteres.");
    if (estado.usuarios.some((x) => x.email.toLowerCase() === d.email.toLowerCase())) throw erro("email_em_uso", "Já existe uma conta com esse e-mail.", 409);
    const u = { id: Math.max(...estado.usuarios.map((x) => x.id)) + 1, email: d.email.trim(), senha: d.senha, nome: d.nome.trim(), papel: "cidadao",
      telefone: d.telefone ?? "", bairro_id: d.bairro_id, vulnerabilidades: d.vulnerabilidades ?? [], contato_emergencia: d.contato_emergencia || null,
      consentimento_lgpd_em: fuso(agora()), criado_em: fuso(agora()) };
    estado.usuarios.push(u); gravar();
    return { token: `demo.${u.id}.${Date.now().toString(36)}`, usuario: publico(u) };
  },
  usuarioDoToken(token) {
    recarregar();
    const id = Number(String(token ?? "").split(".")[1]);
    return publico(estado.usuarios.find((u) => u.id === id));
  },
  territorio: () => structuredClone(TERRITORIO),
  estacoes() {
    recarregar();
    return TERRITORIO.estacoes.map((e) => {
      const s = estado.estacoes[e.id]; const u = s.serie.at(-1);
      const idade = (agoraMs() - new Date(u.ts).getTime()) / 60000;
      return { ...e, estado: idade > 20 ? "offline" : s.bateria_pct < 20 ? "bateria_baixa" : "online", bateria_pct: Math.round(s.bateria_pct), firmware: s.firmware,
        ultima_leitura: { estacao_id: e.id, ts: u.ts, seq: s.seq, nivel_cm: u.nivel_cm, chuva_mm_h: u.chuva_mm_h, umidade_solo_pct: u.umidade_solo_pct, bateria_pct: Math.round(s.bateria_pct), firmware: s.firmware } };
    });
  },
  leituras(estacao_id, horas = 24) {
    recarregar();
    const s = estado.estacoes[estacao_id]; if (!s) throw erro("estacao_desconhecida", "Estação não encontrada.", 404);
    const ini = agoraMs() - horas * 3600e3;
    return s.serie.filter((p) => new Date(p.ts).getTime() >= ini).map((p) => ({ estacao_id, ...p }));
  },
  riscoAtual() { recarregar(); return TERRITORIO.bairros.map(riscoBairro); },
  criarOcorrencia(body, usuario) {
    recarregar();
    const t = String(body.texto ?? "").trim();
    if (t.length < 10) throw erro("texto_curto", "Conte um pouco mais (pelo menos 10 letras).");
    if (t.length > 1000) throw erro("texto_longo", "O relato pode ter no máximo 1000 caracteres.");
    const u = estado.usuarios.find((x) => x.id === usuario?.id) ?? usuario;
    const oc = novaOcorrencia({ ...body, texto: t }, u, "app", agoraMs());
    estado.ocorrencias.unshift(oc); gravar();
    const saida = comPrioridade(oc);
    emitir("ocorrencia", saida);
    return saida;
  },
  ocorrencias(usuario) {
    recarregar();
    if (usuario?.papel === "defesa_civil") {
      return estado.ocorrencias.map(comPrioridade).sort((a, b) => {
        const ordem = { aberta: 0, em_atendimento: 1, resolvida: 2 };
        return ordem[a.status] - ordem[b.status] || b.triagem.prioridade - a.triagem.prioridade || a.criado_em.localeCompare(b.criado_em);
      });
    }
    return estado.ocorrencias.filter((o) => o.usuario_id === usuario?.id).map(comPrioridade);
  },
  atualizarOcorrencia(id, { status }) {
    recarregar();
    const oc = estado.ocorrencias.find((o) => o.id === id); if (!oc) throw erro("nao_encontrada", "Ocorrência não encontrada.", 404);
    if (!["aberta", "em_atendimento", "resolvida"].includes(status)) throw erro("status_invalido", "Status inválido.");
    const ts = fuso(agora());
    if (status !== "aberta" && !oc.atendido_em) {
      oc.atendido_em = ts;
      oc.triagem.prioridade = comPrioridade({ ...oc, status: "aberta" }).triagem.prioridade; // congela a prioridade ao atender
    }
    if (status === "resolvida") oc.resolvido_em = ts;
    oc.status = status; oc.atualizado_em = ts; gravar();
    const saida = comPrioridade(oc);
    emitir("ocorrencia", saida);
    return saida;
  },
  checkin({ status, obs }, usuario) {
    recarregar();
    if (!["seguro", "preciso_ajuda"].includes(status)) throw erro("status_invalido", "Status inválido.");
    const u = estado.usuarios.find((x) => x.id === usuario?.id) ?? usuario;
    const ck = novoCheckin({ status, obs }, u, agoraMs());
    estado.checkins.unshift(ck); gravar();
    emitir("checkin", ck);
    return ck;
  },
  checkins() { recarregar(); return estado.checkins.slice(0, 100); },
  alertas(bairro_id) {
    recarregar();
    const t = agoraMs();
    return estado.alertas.filter((a) => (!bairro_id || a.bairro_id === bairro_id) && new Date(a.valido_ate).getTime() > t);
  },
  historicoAlertas() { recarregar(); return estado.alertas.slice(0, 30); },
  rascunhoAlerta({ bairro_id }) {
    recarregar();
    const b = bairroDe(bairro_id); if (!b) throw erro("bairro_desconhecido", "Bairro não encontrado.", 404);
    const r = riscoBairro(b);
    return { bairro_id, nivel: r.nivel, prob: r.prob, ...redigirAlerta(b, r, abrigoDe(b.id)) };
  },
  emitirAlerta(body, usuario) {
    recarregar();
    if (!body.bairro_id || !body.titulo || !body.mensagem_curta) throw erro("campos_obrigatorios", "Preencha bairro, título e SMS.");
    if (body.mensagem_curta.length > 160) throw erro("sms_longo", "O SMS passou de 160 caracteres.");
    const b = bairroDe(body.bairro_id); const r = riscoBairro(b);
    const al = { id: `AL-${String(++estado.seqAl).padStart(5, "0")}`, bairro_id: b.id, nivel: body.nivel ?? r.nivel, titulo: body.titulo,
      mensagem_curta: body.mensagem_curta, mensagem_completa: body.mensagem_completa ?? body.mensagem_curta, origem: "manual", prob: r.prob,
      emitido_em: fuso(agora()), valido_ate: fuso(new Date(agoraMs() + 6 * 3600e3)), emitido_por: usuario?.id ?? null,
      destinatarios: CADASTRO[b.id].total };
    estado.alertas.unshift(al); estado.alertas = estado.alertas.slice(0, 50); gravar();
    emitir("alerta", al);
    return al;
  },
  indicadores(f) { recarregar(); return calcularIndicadores(f); },
  cenario(c) {
    recarregar();
    if (!CENARIO[c]) throw erro("cenario_invalido", "Cenário inválido.");
    estado.cenario = c; estado.cenario_desde = fuso(agora());
    if (c === "chuva_forte" || c === "enchente") estado.simulados = { oc: 0, ck: 0 };
    gravar();
    emitir("cenario", { cenario: c, desde: estado.cenario_desde });
    if (souLider) passo();
    return { cenario: c, desde: estado.cenario_desde };
  },
  cenarioAtual() { recarregar(); return { cenario: estado.cenario, desde: estado.cenario_desde }; },
};

export { ROTULO };
