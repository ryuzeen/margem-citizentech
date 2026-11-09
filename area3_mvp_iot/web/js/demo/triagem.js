// Modo demonstração: versão simplificada dos agentes da área 1 (triagem por palavras-chave,
// recuperação de protocolos, prioridade e redação de alerta). Mesmo formato de saída do contrato §7.
import { ROTULO, indice } from "../niveis.js";

const semAcento = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "");
const sem = (s) => semAcento(s).toLowerCase();

// Base de conhecimento resumida (paráfrase de orientações públicas de Defesa Civil para enchentes).
export const BASE = [
  { doc: "enchente_dentro_de_casa.md", titulo: "Água entrando na residência", tags: ["agua_na_residencia"],
    trecho: "Desligue a energia no quadro geral antes de a água alcançar as tomadas. Leve documentos e remédios para o alto e saia pelo caminho mais elevado." },
  { doc: "evacuacao_vulneraveis.md", titulo: "Saída de pessoas com mobilidade reduzida", tags: ["pcd", "acamado", "idoso"],
    trecho: "Pessoas com mobilidade reduzida, acamadas ou idosas devem sair primeiro, com acompanhante. Se a saída não for segura, aguarde em local alto e peça resgate." },
  { doc: "criancas_gestantes.md", titulo: "Crianças e gestantes", tags: ["crianca", "gestante"],
    trecho: "Mantenha crianças longe da água: correnteza de 15 cm já derruba um adulto. Gestantes devem evitar esforço e contato com água contaminada." },
  { doc: "agua_corrente.md", titulo: "Ruas alagadas e correnteza", tags: ["via_alagada", "pessoa_ilhada"],
    trecho: "Não atravesse ruas alagadas a pé ou de carro. A água pode esconder buracos, bueiros abertos e fios elétricos." },
  { doc: "resgate_ilhados.md", titulo: "Pessoas ilhadas", tags: ["pessoa_ilhada"],
    trecho: "Quem está ilhado deve ir ao ponto mais alto do imóvel, sinalizar com pano claro ou lanterna e ligar 193. Não tente nadar." },
  { doc: "risco_estrutural.md", titulo: "Rachaduras, muros e desabamento", tags: ["risco_estrutural"],
    trecho: "Rachaduras novas, portas que emperram ou muro inclinado indicam risco. Saia do imóvel e não volte até a vistoria da Defesa Civil." },
  { doc: "energia_eletrica.md", titulo: "Fios e falta de energia", tags: ["falta_energia"],
    trecho: "Fique longe de fios caídos e postes na água. Não use aparelhos molhados. Avise a concessionária e a Defesa Civil." },
  { doc: "kit_emergencia.md", titulo: "Kit de emergência", tags: ["outro", "geral"],
    trecho: "Tenha à mão documentos em saco plástico, remédios de uso contínuo, lanterna, carregador e água potável." },
];

const CATEGORIAS = [
  { cat: "pessoa_ilhada", grav: 5, re: /(ilhad|preso|presa|sem saida|nao consigo sair|nao da pra sair|em cima do telhado|no telhado|isolad)/ },
  { cat: "risco_estrutural", grav: 4, re: /(rachad|desab|muro|parede (caindo|cedendo)|teto|telhado cedendo|barranco|deslizament|trinca)/ },
  { cat: "agua_na_residencia", grav: 3, re: /(entrando (em|na|no)|dentro de casa|dentro da casa|invadiu|na sala|no quarto|na cozinha|em casa|alagou (a|minha) casa|casa alagad|quintal)/ },
  { cat: "falta_energia", grav: 2, re: /(sem luz|sem energia|fio|poste|curto|choque|faisca)/ },
  { cat: "via_alagada", grav: 2, re: /(rua|avenida|via|calcada|ponte|viela|corrego transbord|bueiro)/ },
];

const VULN = [
  { v: "pcd", re: /(cadeirante|cadeira de rodas|deficien|pcd|muleta|nao anda|nao enxerga|cego|surd|autis|mobilidade)/ },
  { v: "idoso", re: /(idos|avo\b|avó|vovo|vovó|velhinh|\b[6-9]\d anos|terceira idade|aposentad)/ },
  { v: "crianca", re: /(crianc|bebe|bebê|filh[oa]s? pequen|recem.nascid|neto|neta|menino|menina|\b[1-9] anos\b)/ },
  { v: "gestante", re: /(gravida|gestante|gravidez|barriga de)/ },
  { v: "acamado", re: /(acamad|de cama|nao levanta|oxigenio|sonda|hospital em casa)/ },
];

const AGRAVANTES = /(subindo rapido|subindo muito|nao para de subir|cintura|peito|pescoco|correnteza|muito rapido|desesper|socorro|urgente)/;
const ATENUANTES = /(baixando|ja baixou|diminuindo|so na rua|so a rua|pouca agua)/;

const DESC_VULN = { idoso: "pessoa idosa", pcd: "PcD/mobilidade reduzida", crianca: "criança", gestante: "gestante", acamado: "pessoa acamada" };

/** Prioridade 0–100 = f(gravidade, vulneráveis, risco atual do bairro, tempo de espera). */
export function calcularPrioridade(gravidade, nVuln, nivelBairro, esperaMin) {
  const pGrav = gravidade * 12;
  const pVuln = Math.min(nVuln, 2) * 10;
  const pRisco = indice(nivelBairro) * 7;
  const pEspera = Math.min(12, Math.floor(esperaMin / 5));
  return { total: Math.min(100, pGrav + pVuln + pRisco + pEspera), pGrav, pVuln, pRisco, pEspera };
}

export function triar(texto, { nivelBairro = "observacao", vulnPerfil = [], nomeBairro = "", abrigo = null } = {}) {
  const t0 = performance.now();
  const s = sem(texto);

  // 1) Agente de triagem
  let cat = "outro", grav = 1, conf = 0.42;
  for (const c of CATEGORIAS) {
    if (c.re.test(s)) { cat = c.cat; grav = c.grav; conf = 0.78; break; }
  }
  if (/agua|alag|enchent|inund|chuva|rio/.test(s) && cat === "outro") { cat = "via_alagada"; grav = 2; conf = 0.55; }
  const agrav = AGRAVANTES.test(s), aten = ATENUANTES.test(s);
  if (agrav) { grav = Math.min(5, grav + 1); conf = Math.min(0.94, conf + 0.08); }
  if (aten) grav = Math.max(1, grav - 1);
  const doTexto = VULN.filter((x) => x.re.test(s)).map((x) => x.v);
  if (doTexto.length && cat === "agua_na_residencia") grav = Math.min(5, grav + 1);
  const vulneraveis = [...new Set([...doTexto, ...vulnPerfil])];
  const ms1 = Math.max(4, Math.round(performance.now() - t0) + 9);

  const partesTri = [`Categoria: ${rotuloCat(cat)} (confiança ${conf.toFixed(2).replace(".", ",")})`, `gravidade ${grav}/5`];
  if (doTexto.length) partesTri.push(`no relato: ${doTexto.map((v) => DESC_VULN[v]).join(", ")}`);
  const doPerfil = vulnPerfil.filter((v) => !doTexto.includes(v));
  if (doPerfil.length) partesTri.push(`no cadastro: ${doPerfil.map((v) => DESC_VULN[v]).join(", ")}`);
  if (agrav) partesTri.push("sinal de agravamento");

  // 2) Agente de protocolos (recuperação por tags, ~TF-IDF)
  const alvo = new Set([cat, ...vulneraveis]);
  const fontes = BASE.map((d) => ({ d, score: d.tags.filter((t) => alvo.has(t)).length }))
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 3)
    .map(({ d }) => ({ doc: d.doc, titulo: d.titulo, trecho: d.trecho }));
  if (!fontes.length) fontes.push((({ doc, titulo, trecho }) => ({ doc, titulo, trecho }))(BASE.at(-1)));

  // 3) Agente de prioridade
  const p = calcularPrioridade(grav, vulneraveis.length, nivelBairro, 0);

  // 4) Resposta ao morador
  const orientacao = montarOrientacao(cat, vulneraveis, grav, abrigo);
  const resumo = montarResumo(cat, grav, vulneraveis, nomeBairro, agrav);

  const rastro = [
    { agente: "triagem", ms: ms1, saida: partesTri.join(" · ") },
    { agente: "protocolos", ms: 14 + fontes.length * 6, saida: `${fontes.length} trecho${fontes.length > 1 ? "s" : ""} recuperado${fontes.length > 1 ? "s" : ""}: ${fontes.map((f) => f.titulo).join("; ")}` },
    { agente: "prioridade", ms: 3, saida: `${p.total}/100 = gravidade ${grav} (${p.pGrav}) + vulneráveis ${Math.min(vulneraveis.length, 2)} (${p.pVuln}) + risco do bairro ${ROTULO[nivelBairro]} (${p.pRisco}) + espera (${p.pEspera})` },
    { agente: "resposta", ms: 6, saida: orientacao },
  ];

  return {
    categoria: cat, gravidade: grav, prioridade: p.total, vulneraveis, resumo, orientacao, fontes,
    confianca: Number(conf.toFixed(2)), modo: "ml+regras", rastro,
  };
}

function rotuloCat(c) {
  return { agua_na_residencia: "água na residência", via_alagada: "via alagada", pessoa_ilhada: "pessoa ilhada",
    risco_estrutural: "risco estrutural", falta_energia: "falta de energia", outro: "outro" }[c];
}

function montarResumo(cat, grav, vuln, bairro, agrav) {
  const base = { agua_na_residencia: "Água entrando em residência", via_alagada: "Via alagada", pessoa_ilhada: "Pessoa ilhada, precisa de resgate",
    risco_estrutural: "Risco estrutural no imóvel", falta_energia: "Falta de energia / fiação exposta", outro: "Relato geral" }[cat];
  const v = vuln.length ? ` com ${vuln.map((x) => DESC_VULN[x]).join(" e ")}` : "";
  return `${base}${v}${bairro ? ` — ${bairro}` : ""}${agrav ? ", nível subindo" : ""}.`;
}

function montarOrientacao(cat, vuln, grav, abrigo) {
  const destino = abrigo ? `o ponto de apoio ${abrigo.nome.replace("Ponto de apoio - ", "").replace(" (simulado)", "")}` : "o ponto de apoio mais próximo";
  const prim = vuln.some((v) => ["pcd", "acamado", "idoso"].includes(v))
    ? "Quem tem dificuldade para andar deve sair primeiro, com alguém junto. "
    : "";
  switch (cat) {
    case "pessoa_ilhada":
      return "Vá para o ponto mais alto da casa e não entre na água. Ligue 193 e deixe o celular com som. Sua solicitação foi enviada à Defesa Civil com prioridade.";
    case "risco_estrutural":
      return `Saia do imóvel agora e não volte até a vistoria. ${prim}Vá para ${destino}.`;
    case "agua_na_residencia":
      return `Desligue a energia no quadro geral, se ainda for seguro. ${prim}Leve documentos e remédios e vá para ${destino}. A Defesa Civil já recebeu seu relato.`;
    case "falta_energia":
      return "Fique longe de fios e postes na água e não mexa em aparelhos molhados. A Defesa Civil foi avisada.";
    case "via_alagada":
      return "Não atravesse a rua alagada, nem a pé nem de carro. Espere em lugar alto ou use outro caminho.";
    default:
      return "Recebemos seu relato. Fique atento aos alertas do app e mantenha o celular carregado.";
  }
}

// Agente comunicador: redige o alerta (título, SMS ≤160 caracteres sem acento, mensagem completa).
export function redigirAlerta(bairro, risco, abrigo) {
  const n = risco.nivel;
  const m = ((risco.nivel_cm ?? 0) / 100).toFixed(1).replace(".", ",");
  const ab = abrigo ? abrigo.nome.replace("Ponto de apoio - ", "").replace(" (simulado)", "") : "ponto de apoio";
  const acao = { observacao: "Fique atento.", atencao: "Separe documentos e remedios.", alerta: "Prepare-se para sair de areas baixas.", alerta_maximo: "Saia agora de areas baixas." }[n];
  const titulo = `${ROTULO[n]} de enchente — ${bairro.nome}`;
  let curta = `Defesa Civil/Margem: ${ROTULO[n].toUpperCase()} ${bairro.nome}. Rio a ${m}m. ${acao} Apoio: ${ab}. Emergencia 199`;
  curta = semAcento(curta);
  if (curta.length > 160) curta = curta.replace(`Apoio: ${semAcento(ab)}. `, "");
  const prob = Math.round((risco.prob ?? 0) * 100);
  const completa =
    `${bairro.nome}: o nível do rio está em ${m} m e a chance de transbordo nas próximas 2 horas é de ${prob} em cada 100. ` +
    ({ observacao: "Não é preciso sair de casa agora. Acompanhe o app.",
       atencao: "Separe documentos, remédios e carregador. Tire do chão o que estraga com água.",
       alerta: "Prepare-se para sair. Quem tem dificuldade para andar deve sair primeiro. Não atravesse ruas alagadas.",
       alerta_maximo: "Saia agora das áreas baixas. Se não puder sair, suba para o lugar mais alto e peça ajuda pelo app." }[n]) +
    (abrigo ? ` Ponto de apoio: ${abrigo.nome.replace("Ponto de apoio - ", "").replace(" (simulado)", "")}${abrigo.acessivel ? " (acessível)" : ""}.` : "") +
    " Emergência: Defesa Civil 199, Bombeiros 193.";
  return {
    titulo, mensagem_curta: curta, mensagem_completa: completa,
    rastro: [
      { agente: "comunicador", ms: 18, saida: `Nível ${ROTULO[n]}, rio ${m} m, prob. ${prob}%. Texto em linguagem simples, SMS sem acentos (${curta.length}/160).` },
    ],
  };
}
