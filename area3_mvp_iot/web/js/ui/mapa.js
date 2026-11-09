// Mapa com Leaflet (vendor/leaflet, BSD-2). Base OpenStreetMap quando há internet; sem internet,
// mostra curvas de nível + traçado aproximado do Tietê desenhado pelo próprio app.
import { ROTULO, indice } from "../niveis.js";
import { esc } from "./util.js";

const COR = ["--risco-0", "--risco-1", "--risco-2", "--risco-3"];
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
// Traçado APROXIMADO do Rio Tietê no trecho (só para orientação visual)
const TIETE = [[-23.4935, -46.452], [-23.4918, -46.441], [-23.4896, -46.4318], [-23.4862, -46.4248], [-23.4822, -46.4196], [-23.4808, -46.4128], [-23.4826, -46.4062], [-23.4846, -46.4012], [-23.4842, -46.3935], [-23.4818, -46.384]];

export function criarMapa(el, territorio, { tema = "claro", aoSelecionarBairro = null, mostrar = { bairros: true, estacoes: true, abrigos: true } } = {}) {
  if (!window.L) { el.innerHTML = `<p class="mapa-erro">Não foi possível carregar o mapa.</p>`; return null; }
  const L = window.L;
  const mapa = L.map(el, { zoomControl: true, attributionControl: true, scrollWheelZoom: tema === "escuro", minZoom: 12, maxZoom: 18 })
    .setView([territorio.centro.lat, territorio.centro.lng], territorio.centro.zoom);
  mapa.attributionControl.setPrefix(false);

  el.classList.add("mapa", `mapa-${tema}`);
  let falhas = 0;
  const base = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>', crossOrigin: true,
  });
  const semBase = (v) => el.classList.toggle("sem-base", v);
  base.on("tileerror", () => { if (++falhas >= 3) semBase(true); });
  base.on("tileload", () => { falhas = 0; semBase(false); });
  if (navigator.onLine) base.addTo(mapa); else semBase(true);
  addEventListener("online", () => { if (!mapa.hasLayer(base)) base.addTo(mapa); });
  addEventListener("offline", () => semBase(true));

  const aviso = L.control({ position: "bottomleft" });
  aviso.onAdd = () => { const d = L.DomUtil.create("div", "mapa-aviso"); d.textContent = "Sem internet: mapa base indisponível. Posições aproximadas."; return d; };
  aviso.addTo(mapa);

  L.polyline(TIETE, { color: css("--agua"), weight: tema === "escuro" ? 5 : 7, opacity: 0.55, interactive: false, className: "tiete" }).addTo(mapa);

  const camadaBairros = L.layerGroup().addTo(mapa);
  const camadaEst = L.layerGroup().addTo(mapa);
  const camadaAbr = L.layerGroup().addTo(mapa);
  const bairros = new Map(), estacoes = new Map();

  for (const b of territorio.bairros) {
    const c = L.circle([b.lat, b.lng], { radius: 520, weight: 2, color: css("--risco-0"), fillColor: css("--risco-0"), fillOpacity: 0.16, className: "bairro-area" });
    c.bindTooltip("", { permanent: true, direction: "center", className: "rotulo-bairro", opacity: 1 });
    if (aoSelecionarBairro) c.on("click", () => aoSelecionarBairro(b.id));
    c.addTo(camadaBairros);
    bairros.set(b.id, { c, b });
  }
  for (const e of territorio.estacoes) {
    const m = L.marker([e.lat, e.lng], { icon: iconeEstacao(e, null), keyboard: true, title: e.nome, riseOnHover: true }).addTo(camadaEst);
    m.bindPopup("");
    estacoes.set(e.id, { m, e });
  }
  for (const a of territorio.abrigos) {
    L.marker([a.lat, a.lng], {
      title: a.nome, keyboard: true,
      icon: L.divIcon({ className: "pino-abrigo", iconSize: [34, 34], iconAnchor: [17, 17],
        html: `<span class="pino-abrigo-corpo${a.acessivel ? " acessivel" : ""}"><svg class="ico" aria-hidden="true"><use href="#i-house"/></svg></span>` }),
    }).bindPopup(`<strong>${esc(a.nome.replace(" (simulado)", ""))}</strong><br>Capacidade: ${a.capacidade} pessoas<br>${a.acessivel ? "Acessível para cadeira de rodas" : "Sem acessibilidade completa"}<br><small>Ponto de apoio simulado</small>`)
      .addTo(camadaAbr);
  }
  const visivel = (camada, v) => (v ? camada.addTo(mapa) : camada.remove());
  visivel(camadaBairros, mostrar.bairros); visivel(camadaEst, mostrar.estacoes); visivel(camadaAbr, mostrar.abrigos);

  return {
    mapa,
    camadas: { bairros: camadaBairros, estacoes: camadaEst, abrigos: camadaAbr },
    alternar(nome, v) { visivel({ bairros: camadaBairros, estacoes: camadaEst, abrigos: camadaAbr }[nome], v); },
    atualizarRisco(riscos) {
      for (const r of riscos) {
        const x = bairros.get(r.bairro_id); if (!x) continue;
        const n = indice(r.nivel), cor = css(COR[n]);
        x.c.setStyle({ color: cor, fillColor: cor, fillOpacity: 0.12 + n * 0.06, dashArray: n >= 2 ? null : "4 4" });
        x.c.setTooltipContent(`<span class="rb-nome">${esc(x.b.nome)}</span><span class="rb-nivel" data-n="${n}">${ROTULO[r.nivel]}</span>`);
        const est = estacoes.get(r.estacao_id ?? x.b.estacao_id);
        if (est && r.nivel_cm != null) est.m.setIcon(iconeEstacao(est.e, r));
        if (est) est.m.setPopupContent(popupEstacao(est.e, r));
      }
    },
    focar(lat, lng, zoom = 15) { mapa.setView([lat, lng], zoom); },
    redimensionar() { mapa.invalidateSize(); },
  };
}

function iconeEstacao(e, r) {
  const n = r ? indice(r.nivel) : 0;
  const m = r?.nivel_cm != null ? (r.nivel_cm / 100).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—";
  const pct = r ? Math.min(1, r.nivel_cm / e.cota_transbordo_cm) : 0;
  return window.L.divIcon({
    className: "pino-estacao", iconSize: [74, 34], iconAnchor: [12, 30],
    html: `<span class="pe" data-n="${n}"><span class="pe-regua"><i style="height:${Math.round(pct * 100)}%"></i></span><span class="pe-valor">${m}<small> m</small></span></span>`,
  });
}

function popupEstacao(e, r) {
  const f = (cm) => (cm / 100).toLocaleString("pt-BR", { minimumFractionDigits: 2 });
  return `<strong>${esc(e.nome)}</strong><br>Nível: <b>${f(r.nivel_cm)} m</b> (${Math.round(r.pct_cota_alerta * 100)}% da cota de alerta)<br>Alerta ${f(e.cota_alerta_cm)} m · Transbordo ${f(e.cota_transbordo_cm)} m<br>Risco: ${ROTULO[r.nivel]} · chance de transbordo em 2 h: ${Math.round(r.prob * 100)} em 100`;
}
