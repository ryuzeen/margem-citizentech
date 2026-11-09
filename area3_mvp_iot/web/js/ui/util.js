// Utilitários de UI: DOM seguro, formatação PT-BR, ícones, avisos.
import { SPRITE } from "../../vendor/lucide/sprite.js";
import { indice, ROTULO } from "../niveis.js";

export const $ = (sel, raiz = document) => raiz.querySelector(sel);
export const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ESC[c]);

/** Template literal que escapa interpolações (use raw(...) para HTML confiável). */
export function html(partes, ...vals) {
  let out = "";
  partes.forEach((p, i) => {
    out += p;
    if (i < vals.length) {
      const v = vals[i];
      if (v == null || v === false) return;
      if (Array.isArray(v)) out += v.map((x) => (x && x.__raw ? x.s : esc(x))).join("");
      else out += v && v.__raw ? v.s : esc(v);
    }
  });
  return { __raw: true, s: out, toString() { return out; } };
}
export const raw = (s) => ({ __raw: true, s: String(s), toString() { return String(s); } });
export function render(alvo, conteudo) { alvo.innerHTML = String(conteudo); return alvo; }

export function injetarIcones() {
  if (document.getElementById("sprite-lucide")) return;
  const d = document.createElement("div");
  d.id = "sprite-lucide";
  d.setAttribute("aria-hidden", "true");
  d.innerHTML = SPRITE;
  document.body.prepend(d);
}
export const ico = (nome, cls = "") => raw(`<svg class="ico ${cls}" aria-hidden="true" focusable="false"><use href="#i-${nome}"/></svg>`);

// ---------- Formatação ----------
const nf1 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const nf0 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
export const n0 = (v) => nf0.format(v ?? 0);
export const n1 = (v) => nf1.format(v ?? 0);
export const metros = (cm) => `${nf2.format((cm ?? 0) / 100)} m`;
export const pct = (v) => `${nf0.format(Math.round((v ?? 0) * 100))}%`;

export const dataDe = (iso) => (iso instanceof Date ? iso : new Date(iso));
export const hora = (iso) => dataDe(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
export const dataHora = (iso) => dataDe(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

export function ha(iso, agora = Date.now()) {
  const s = Math.max(0, Math.round((agora - dataDe(iso).getTime()) / 1000));
  if (s < 60) return "agora";
  const m = Math.round(s / 60);
  if (m < 60) return `há ${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `há ${h} h${m % 60 ? ` ${m % 60} min` : ""}`;
  const d = Math.floor(h / 24);
  return `há ${d} dia${d > 1 ? "s" : ""}`;
}
export function duracao(min) {
  min = Math.max(0, Math.round(min));
  if (min < 60) return `${min} min`;
  return `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, "0")}`;
}

export function distanciaM(a, b) {
  const R = 6371000, r = Math.PI / 180;
  const dLat = (b.lat - a.lat) * r, dLng = (b.lng - a.lng) * r;
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
}
export const distTexto = (m) => (m < 1000 ? `${Math.round(m / 10) * 10} m` : `${n1(m / 1000)} km`);

/** Etiqueta de nível: cor + rótulo + degraus (o risco nunca depende só da cor). */
export const etiquetaNivel = (nivel) =>
  html`<span class="nivel" data-n="${indice(nivel)}"><span class="degraus" aria-hidden="true"><i></i><i></i><i></i><i></i></span>${ROTULO[nivel] ?? nivel}</span>`;

// ---------- Avisos (toasts) ----------
let caixa;
export function avisar(texto, { icone = "info", ms = 4200 } = {}) {
  if (!caixa) {
    caixa = document.createElement("div");
    caixa.className = "avisos";
    caixa.setAttribute("role", "status");
    caixa.setAttribute("aria-live", "polite");
    document.body.append(caixa);
  }
  const el = document.createElement("div");
  el.className = "aviso";
  el.innerHTML = `${ico(icone)}<span>${esc(texto)}</span>`;
  caixa.append(el);
  setTimeout(() => { el.classList.add("saindo"); setTimeout(() => el.remove(), 180); }, ms);
}

export function mascararTelefone(t) {
  const d = String(t ?? "").replace(/\D/g, "");
  if (d.length < 8) return "(••) •••••-••••";
  return `(${d.slice(0, 2)}) •••••-${d.slice(-4)}`;
}

export function debounce(fn, ms = 200) {
  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

export const reduzMovimento = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
