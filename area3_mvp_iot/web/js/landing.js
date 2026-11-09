// Landing: mostra o estado atual do rio no Jardim Pantanal (API real ou modo demonstração).
import { apiPara } from "./api.js";
import { $, injetarIcones, metros, etiquetaNivel } from "./ui/util.js";
import { chanceSimples, RESUMO } from "./niveis.js";
import { criarRegua } from "./ui/regua.js";

const api = apiPara("app");

async function iniciar() {
  injetarIcones();
  const modo = await api.iniciar();
  if (modo === "demo") $("#agora-modo").hidden = false;
  const terr = await api.territorio();
  const b = terr.bairros.find((x) => x.id === "jardim-pantanal");
  const e = terr.estacoes.find((x) => x.id === b.estacao_id);
  const regua = criarRegua($("#ab-regua"), { cotaAlerta: e.cota_alerta_cm, cotaTransbordo: e.cota_transbordo_cm, titulo: "Régua do rio no Jardim Pantanal" });
  const mostrar = (riscos) => {
    const r = riscos.find((x) => x.bairro_id === b.id); if (!r) return;
    if (r.nivel_cm != null) { regua.atualizar(r.nivel_cm); $("#ab-nivel").textContent = metros(r.nivel_cm); }
    $("#ab-risco").innerHTML = String(etiquetaNivel(r.nivel));
    const c = chanceSimples(r.prob);
    $("#ab-chance").textContent = `${RESUMO[r.nivel]} Chance de transbordar nas próximas 2 horas: ${c.palavra} (${c.frase}).`;
  };
  mostrar(await api.riscoAtual());
  api.on(({ tipo, dados }) => { if (tipo === "risco") mostrar(dados); });
}
iniciar().catch(() => { $(".ab-agora")?.setAttribute("hidden", ""); });
