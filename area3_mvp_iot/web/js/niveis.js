// Níveis de risco (CONTRATOS §3) e textos em linguagem simples, compartilhados por app e console.

export const NIVEIS = ["observacao", "atencao", "alerta", "alerta_maximo"];

export const ROTULO = {
  observacao: "Observação",
  atencao: "Atenção",
  alerta: "Alerta",
  alerta_maximo: "Alerta máximo",
};

export const indice = (nivel) => Math.max(0, NIVEIS.indexOf(nivel));

export function nivelPorCota(nivelCm, cotaAlerta, cotaTransbordo) {
  if (nivelCm >= cotaTransbordo) return "alerta_maximo";
  if (nivelCm >= cotaAlerta) return "alerta";
  if (nivelCm >= 0.6 * cotaAlerta) return "atencao";
  return "observacao";
}

export function nivelPorProb(prob) {
  if (prob >= 0.85) return "alerta_maximo";
  if (prob >= 0.6) return "alerta";
  if (prob >= 0.35) return "atencao";
  return "observacao";
}

export const maiorNivel = (...n) => n.reduce((a, b) => (indice(b) > indice(a) ? b : a), "observacao");

/** Frase curta para a chance de transbordo, em frequência natural ("72 em cada 100"). */
export function chanceSimples(prob) {
  const p = Math.round((prob ?? 0) * 100);
  let palavra = "muito baixa";
  if (prob >= 0.85) palavra = "muito alta";
  else if (prob >= 0.6) palavra = "alta";
  else if (prob >= 0.35) palavra = "moderada";
  else if (prob >= 0.15) palavra = "baixa";
  return { palavra, p, frase: `${p} em cada 100` };
}

export const RESUMO = {
  observacao: "O rio está dentro do normal.",
  atencao: "O rio está subindo. Fique de olho e se prepare.",
  alerta: "O rio pode transbordar. Prepare-se para sair.",
  alerta_maximo: "Risco de transbordo agora. Saia para um lugar seguro.",
};

export const O_QUE_FAZER = {
  observacao: [
    "Mantenha o celular carregado e o som de alerta ligado.",
    "Guarde documentos e remédios num saco plástico, num lugar alto.",
    "Saiba o caminho até o ponto de apoio mais próximo.",
  ],
  atencao: [
    "Separe numa mochila: documentos, remédios, carregador e água.",
    "Tire do chão o que estraga com água: colchão, eletrônicos, comida.",
    "Combine com a família e os vizinhos onde vocês vão se encontrar.",
  ],
  alerta: [
    "Prepare-se para sair. Quem tem dificuldade para andar sai primeiro.",
    "Se a água chegar perto das tomadas, desligue a energia no quadro geral.",
    "Não atravesse rua alagada, nem a pé nem de carro.",
  ],
  alerta_maximo: [
    "Saia agora e vá para o ponto de apoio indicado abaixo.",
    "Se não der para sair, suba para o lugar mais alto e toque em “Preciso de ajuda”.",
    "Emergência: Defesa Civil 199 · Bombeiros 193 · SAMU 192.",
  ],
};

export const TENDENCIA = { subindo: "subindo", estavel: "estável", descendo: "descendo" };

export const CATEGORIA = {
  agua_na_residencia: "Água na residência",
  via_alagada: "Via alagada",
  pessoa_ilhada: "Pessoa ilhada",
  risco_estrutural: "Risco estrutural",
  falta_energia: "Falta de energia",
  outro: "Outro",
};

export const VULNERAVEL = {
  idoso: "Pessoa idosa",
  pcd: "PcD / mobilidade reduzida",
  crianca: "Criança pequena",
  gestante: "Gestante",
  acamado: "Pessoa acamada",
};

export const STATUS_OC = { aberta: "Aberta", em_atendimento: "Em atendimento", resolvida: "Resolvida" };

export const CENARIOS = {
  normal: { rotulo: "Normal", desc: "Tempo seco, rio no nível de base." },
  chuva_forte: { rotulo: "Chuva forte", desc: "Chuva de 25 a 40 mm/h. Rio sobe até perto da cota de alerta." },
  enchente: { rotulo: "Enchente", desc: "Chuva extrema. Pantanal, Itaim e Romano passam da cota de transbordo." },
  recuperacao: { rotulo: "Recuperação", desc: "A chuva para e o rio desce aos poucos." },
};
