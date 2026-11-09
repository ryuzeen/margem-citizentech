// Régua linimétrica em SVG: traços em "E" a cada 10 cm, metros alternando tinta/vermelho como nas réguas
// pintadas na margem do rio, faixa de risco por posição, cotas de alerta/transbordo e lâmina d'água animada.

const NS = "http://www.w3.org/2000/svg";
let uid = 0;

const fmt = (cm) => (cm / 100).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function criarRegua(alvo, { cotaAlerta, cotaTransbordo, maxCm, compacta = false, titulo = "Régua do rio" }) {
  const id = `rg${++uid}`;
  const max = maxCm ?? Math.ceil((cotaTransbordo * 1.22) / 50) * 50;
  const W = compacta ? 120 : 152, TOP = 16, BOT = compacta ? 300 : 416, H = BOT - TOP;
  const X0 = compacta ? 30 : 30, LARG = compacta ? 34 : 44, X1 = X0 + LARG;
  const y = (cm) => TOP + (1 - Math.min(cm, max) / max) * H;

  let s = `<svg class="regua" viewBox="0 0 ${W} ${BOT + 14}" preserveAspectRatio="xMidYMid meet" role="img" aria-labelledby="${id}-t">
  <title id="${id}-t">${titulo}</title>
  <defs><clipPath id="${id}-c"><rect x="0" y="${TOP}" width="${W}" height="${H}"/></clipPath></defs>`;

  // Faixa de risco por posição (verde → vermelho) à direita da régua
  const faixas = [[0, 0.6 * cotaAlerta, "--risco-0"], [0.6 * cotaAlerta, cotaAlerta, "--risco-1"], [cotaAlerta, cotaTransbordo, "--risco-2"], [cotaTransbordo, max, "--risco-3"]];
  for (const [a, b, cor] of faixas) s += `<rect x="${X1 + 4}" y="${y(b)}" width="5" height="${y(a) - y(b)}" fill="var(${cor})"/>`;

  // Corpo da régua
  s += `<rect x="${X0}" y="${TOP}" width="${LARG}" height="${H}" fill="#fff" stroke="var(--tinta)" stroke-width="1.2"/>`;
  // Traços em E por decímetro, cor alterna a cada metro (tinta / vermelho)
  const dente = LARG * 0.5;
  for (let cm = 0; cm < max; cm += 10) {
    const cor = Math.floor(cm / 100) % 2 === 0 ? "var(--tinta)" : "var(--risco-3)";
    const yb = y(cm), u = (y(cm) - y(cm + 10)) / 10; // px por cm
    const xE = (cm / 10) % 2 === 0 ? X0 : X0 + LARG - dente; // E alterna lado como na régua real
    const xBar = (cm / 10) % 2 === 0 ? X0 : X0 + LARG - LARG * 0.12;
    s += `<rect x="${xBar}" y="${yb - 10 * u}" width="${LARG * 0.12}" height="${10 * u}" fill="${cor}"/>`;
    for (const k of [0, 4, 8]) s += `<rect x="${xE}" y="${yb - (k + 2) * u}" width="${dente}" height="${2 * u}" fill="${cor}"/>`;
  }
  // Números a cada 50 cm (à esquerda)
  const passo = compacta ? 100 : 50;
  for (let cm = 0; cm <= max; cm += passo) {
    const metro = cm % 100 === 0;
    s += `<text x="${X0 - 7}" y="${y(cm) + 4}" text-anchor="end" font-size="${metro ? 13 : 10}" font-weight="${metro ? 600 : 400}" fill="${metro ? "var(--tinta)" : "var(--tinta-2)"}">${metro ? cm / 100 : (cm / 100).toLocaleString("pt-BR")}</text>`;
    s += `<line x1="${X0 - 4}" x2="${X0}" y1="${y(cm)}" y2="${y(cm)}" stroke="var(--tinta)" stroke-width="1"/>`;
  }
  if (!compacta) s += `<text x="${X0 - 7}" y="${TOP - 2}" text-anchor="end" font-size="10" fill="var(--tinta-2)">m</text>`;

  // Lâmina d'água (grupo movido por transform)
  const onda = (amp, fase) => {
    let d = `M -80 ${amp}`;
    for (let x = -80; x <= W + 80; x += 10) d += ` L ${x} ${(Math.sin((x + fase) / 40 * Math.PI * 2) * amp).toFixed(2)}`;
    return d;
  };
  s += `<g clip-path="url(#${id}-c)"><g class="agua" style="transform: translateY(${BOT}px)">
    <path class="onda onda-2" d="${onda(2.2, 13)} L ${W + 80} ${H + 40} L -80 ${H + 40} Z" fill="var(--agua-media)" opacity="0.32"/>
    <path class="onda" d="${onda(1.6, 0)} L ${W + 80} ${H + 40} L -80 ${H + 40} Z" fill="var(--agua)" opacity="0.30"/>
    <path class="onda" d="${onda(1.6, 0)}" fill="none" stroke="var(--agua)" stroke-width="2"/>
  </g></g>`;

  // Cotas
  const cota = (cm, rot, cor) => `<g>
    <line x1="${X0 - 4}" x2="${W - 2}" y1="${y(cm)}" y2="${y(cm)}" stroke="var(${cor})" stroke-width="2" stroke-dasharray="${compacta ? "3 3" : "6 4"}"/>
    ${compacta ? "" : `<text x="${W - 1}" y="${y(cm) - 6}" text-anchor="end" font-size="10" font-weight="600" fill="var(${cor}-texto)">${rot}</text>
    <text x="${W - 1}" y="${y(cm) + 14}" text-anchor="end" font-size="11" font-weight="500" fill="var(${cor}-texto)">${fmt(cm)}</text>`}
  </g>`;
  s += cota(cotaAlerta, "ALERTA", "--risco-2") + cota(cotaTransbordo, "TRANSBORDO", "--risco-3");

  // Marcador do nível atual
  s += `<g class="marcador" style="transform: translateY(${BOT}px)">
    <path d="M ${X1 + 12} 0 l 9 -6 v 12 z" fill="var(--tinta)"/>
  </g>`;
  s += `<line x1="${X0 - 4}" x2="${X1 + 9}" y1="${BOT}" y2="${BOT}" stroke="var(--tinta)" stroke-width="1.2"/></svg>`;

  alvo.innerHTML = s;
  const agua = alvo.querySelector(".agua");
  const marc = alvo.querySelector(".marcador");
  let ultimo = null;
  return {
    max,
    atualizar(nivelCm) {
      const yy = y(Math.max(0, nivelCm));
      // Primeira vez: sobe a partir do fundo (efeito de "encher"); depois, só a diferença.
      const aplicar = () => { agua.style.transform = `translateY(${yy}px)`; marc.style.transform = `translateY(${yy}px)`; };
      if (ultimo === null) requestAnimationFrame(() => requestAnimationFrame(aplicar)); else aplicar();
      ultimo = nivelCm;
    },
  };
}
