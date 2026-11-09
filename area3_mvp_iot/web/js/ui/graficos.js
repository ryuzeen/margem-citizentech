// Gráficos em SVG próprio (sem biblioteca). Cores vêm de variáveis CSS do contêiner:
// --g-texto, --g-grade, --g-serie, --g-area, --g-alerta, --g-transbordo.
import { esc } from "./util.js";

const nf = (v, d = 0) => Number(v).toLocaleString("pt-BR", { maximumFractionDigits: d, minimumFractionDigits: d });
const horaCurta = (iso) => new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
const diaCurto = (iso) => new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });

/** Linha mínima (estações): nível nas últimas horas, com a cota de alerta marcada. */
export function sparkline(serie, { w = 160, h = 40, cota = null, max = null } = {}) {
  if (!serie?.length) return `<svg width="${w}" height="${h}" aria-hidden="true"></svg>`;
  const vals = serie.map((p) => p.nivel_cm);
  const lo = Math.min(...vals, cota ?? Infinity) * 0.92, hi = Math.max(max ?? 0, ...vals, cota ?? 0) * 1.04;
  const x = (i) => (i / (vals.length - 1)) * (w - 4) + 2;
  const y = (v) => h - 3 - ((v - lo) / (hi - lo || 1)) * (h - 6);
  const d = vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join("");
  const area = `${d}L${x(vals.length - 1)} ${h}L${x(0)} ${h}Z`;
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" preserveAspectRatio="none" aria-hidden="true">
    <path d="${area}" fill="var(--g-area)"/>
    ${cota ? `<line x1="0" x2="${w}" y1="${y(cota)}" y2="${y(cota)}" stroke="var(--g-alerta)" stroke-width="1" stroke-dasharray="3 3"/>` : ""}
    <path d="${d}" fill="none" stroke="var(--g-serie)" stroke-width="1.6" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>
    <circle cx="${x(vals.length - 1)}" cy="${y(vals.at(-1))}" r="2.6" fill="var(--g-serie)"/>
  </svg>`;
}

/** Série de nível com cotas, eixos e pontos com dica nativa (title). */
export function linhaNivel(serie, { w = 640, h = 240, cotaAlerta, cotaTransbordo, agregacao = "5min", titulo = "" } = {}) {
  if (!serie?.length) return `<p class="g-vazio">Sem leituras neste período.</p>`;
  const pad = { l: 44, r: 12, t: 12, b: 26 };
  const vals = serie.map((p) => p.nivel_cm);
  const hi = Math.max(...vals, cotaTransbordo ?? 0) * 1.08, lo = 0;
  const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
  const x = (i) => pad.l + (serie.length === 1 ? iw / 2 : (i / (serie.length - 1)) * iw);
  const y = (v) => pad.t + ih - ((v - lo) / (hi - lo)) * ih;
  const d = vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join("");
  let s = `<svg class="g-linha" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(titulo)}">`;
  // grade horizontal a cada metro (ou 50 cm)
  const passo = hi > 300 ? 100 : 50;
  for (let v = 0; v <= hi; v += passo) {
    s += `<line x1="${pad.l}" x2="${w - pad.r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--g-grade)" stroke-width="1"/>`;
    s += `<text x="${pad.l - 8}" y="${y(v) + 4}" text-anchor="end" class="g-eixo">${nf(v / 100, v % 100 ? 1 : 0)} m</text>`;
  }
  // rótulos do eixo x (5 marcas): hora quando a série cobre até ~1,5 dia; senão, dia
  const spanH = (new Date(serie.at(-1).ts) - new Date(serie[0].ts)) / 3600e3;
  const curto = spanH <= 36 ? horaCurta : diaCurto;
  const dica = spanH <= 36 ? horaCurta : (ts) => `${diaCurto(ts)} ${horaCurta(ts)}`;
  const marcas = 5;
  for (let k = 0; k < marcas; k++) {
    const i = Math.round((k / (marcas - 1)) * (serie.length - 1));
    const t = curto(serie[i].ts);
    s += `<text x="${x(i)}" y="${h - 6}" text-anchor="${k === 0 ? "start" : k === marcas - 1 ? "end" : "middle"}" class="g-eixo">${t}</text>`;
  }
  s += `<path d="${d}L${x(serie.length - 1)} ${y(0)}L${x(0)} ${y(0)}Z" fill="var(--g-area)"/>`;
  if (cotaAlerta) s += `<line x1="${pad.l}" x2="${w - pad.r}" y1="${y(cotaAlerta)}" y2="${y(cotaAlerta)}" stroke="var(--g-alerta)" stroke-width="1.5" stroke-dasharray="6 4"/><text x="${w - pad.r}" y="${y(cotaAlerta) - 5}" text-anchor="end" class="g-cota" fill="var(--g-alerta)">alerta ${nf(cotaAlerta / 100, 2)} m</text>`;
  if (cotaTransbordo) s += `<line x1="${pad.l}" x2="${w - pad.r}" y1="${y(cotaTransbordo)}" y2="${y(cotaTransbordo)}" stroke="var(--g-transbordo)" stroke-width="1.5" stroke-dasharray="6 4"/><text x="${w - pad.r}" y="${y(cotaTransbordo) - 5}" text-anchor="end" class="g-cota" fill="var(--g-transbordo)">transbordo ${nf(cotaTransbordo / 100, 2)} m</text>`;
  s += `<path d="${d}" fill="none" stroke="var(--g-serie)" stroke-width="2" stroke-linejoin="round"/>`;
  // alvos de dica (amostrados)
  const salto = Math.max(1, Math.floor(serie.length / 48));
  for (let i = 0; i < serie.length; i += salto) {
    const t = agregacao === "max_diario" ? diaCurto(serie[i].ts) : dica(serie[i].ts);
    s += `<g class="g-ponto"><rect x="${x(i) - (iw / serie.length) * salto / 2}" y="${pad.t}" width="${Math.max(4, (iw / serie.length) * salto)}" height="${ih}" fill="transparent"/><circle cx="${x(i)}" cy="${y(vals[i])}" r="3.5"/><title>${t}: ${nf(vals[i] / 100, 2)} m</title></g>`;
  }
  s += `<circle cx="${x(serie.length - 1)}" cy="${y(vals.at(-1))}" r="4" fill="var(--g-serie)" stroke="var(--g-fundo)" stroke-width="2"/>`;
  return s + `</svg>`;
}

/** Barras horizontais empilhadas (ex.: ocorrências por categoria × gravidade). */
export function barrasEmpilhadas(linhas, { chaves, cores, rotulos, w = 520, alturaLinha = 30 } = {}) {
  const total = Math.max(1, ...linhas.map((l) => chaves.reduce((s, k) => s + (l.valores[k] ?? 0), 0)));
  const padL = 150, padR = 40, iw = w - padL - padR;
  const h = linhas.length * alturaLinha + 4;
  let s = `<svg class="g-barras" viewBox="0 0 ${w} ${h}" role="img" aria-label="Ocorrências por categoria e gravidade">`;
  linhas.forEach((l, i) => {
    const y0 = i * alturaLinha + 6;
    let x = padL, soma = 0;
    s += `<text x="${padL - 10}" y="${y0 + 13}" text-anchor="end" class="g-rotulo">${esc(l.rotulo)}</text>`;
    chaves.forEach((k, j) => {
      const v = l.valores[k] ?? 0; if (!v) return;
      const ww = (v / total) * iw;
      s += `<rect x="${x}" y="${y0}" width="${Math.max(1.5, ww - 1.5)}" height="18" rx="2" fill="${cores[j]}"><title>${esc(l.rotulo)} · ${rotulos[j]}: ${v}</title></rect>`;
      x += ww; soma += v;
    });
    s += `<text x="${x + 6}" y="${y0 + 13}" class="g-valor">${soma}</text>`;
  });
  return s + `</svg>`;
}

/** Colunas simples (ex.: tempo médio por semana) com linha de meta. */
export function colunas(dados, { w = 520, h = 180, meta = null, sufixo = "", rotuloX = (d) => d.rotulo } = {}) {
  const vals = dados.map((d) => d.valor ?? 0);
  const hi = Math.max(meta ?? 0, ...vals) * 1.15 || 1;
  const pad = { l: 34, r: 8, t: 10, b: 24 };
  const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
  const bw = iw / dados.length;
  const y = (v) => pad.t + ih - (v / hi) * ih;
  let s = `<svg class="g-colunas" viewBox="0 0 ${w} ${h}" role="img" aria-label="Série por período">`;
  const passo = [1, 2, 5, 10, 20, 25, 50, 100, 200, 500].find((p) => hi / p <= 4) ?? Math.ceil(hi / 4);
  const marcas = []; for (let v = 0; v <= hi; v += passo) marcas.push(v);
  for (const v of marcas) s += `<line x1="${pad.l}" x2="${w - pad.r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--g-grade)"/><text x="${pad.l - 6}" y="${y(v) + 4}" text-anchor="end" class="g-eixo">${nf(v)}</text>`;
  dados.forEach((d, i) => {
    const v = d.valor; const x = pad.l + i * bw + bw * 0.18;
    if (v != null) s += `<rect x="${x}" y="${y(v)}" width="${bw * 0.64}" height="${Math.max(0, y(0) - y(v))}" rx="2" fill="${meta != null && v > meta ? "var(--g-ruim)" : "var(--g-serie)"}"><title>${esc(rotuloX(d))}: ${nf(v, 1)}${sufixo}</title></rect>`;
    if (i % Math.ceil(dados.length / 7) === 0) s += `<text x="${x + bw * 0.32}" y="${h - 6}" text-anchor="middle" class="g-eixo">${esc(rotuloX(d))}</text>`;
  });
  if (meta != null) s += `<line x1="${pad.l}" x2="${w - pad.r}" y1="${y(meta)}" y2="${y(meta)}" stroke="var(--g-texto)" stroke-dasharray="4 3"/><text x="${w - pad.r}" y="${y(meta) - 5}" text-anchor="end" class="g-cota" fill="var(--g-texto)">meta ${meta}${sufixo}</text>`;
  return s + `</svg>`;
}
