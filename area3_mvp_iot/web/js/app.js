// Margem — app do morador. Rotas por hash: #/entrar, #/cadastro, #/alerta, #/mapa, #/relatar, #/relatos
import { apiPara } from "./api.js";
import { $, $$, esc, html, raw, render, ico, injetarIcones, avisar, metros, n0, n1, hora, ha, distanciaM, distTexto, etiquetaNivel, reduzMovimento } from "./ui/util.js";
import { ROTULO, RESUMO, O_QUE_FAZER, indice, chanceSimples, CATEGORIA, VULNERAVEL, STATUS_OC, TENDENCIA } from "./niveis.js";
import { criarRegua } from "./ui/regua.js";
import { criarMapa } from "./ui/mapa.js";

const api = apiPara("app");
const S = { territorio: null, risco: [], estacoes: [], alertas: [], usuario: null, rota: null, regua: null, mapa: null, ultimoNivel: null, falando: false };
const main = $("#conteudo");

// ---------- Preferências de acessibilidade ----------
const pref = (() => { try { return JSON.parse(localStorage.getItem("margem:pref") || "{}"); } catch { return {}; } })();
function aplicarPref() {
  document.documentElement.dataset.fonte = pref.fonte ? "grande" : "";
  document.documentElement.dataset.contraste = pref.contraste ? "alto" : "";
  $("#bt-fonte").setAttribute("aria-pressed", String(!!pref.fonte));
  $("#bt-contraste").setAttribute("aria-pressed", String(!!pref.contraste));
  localStorage.setItem("margem:pref", JSON.stringify(pref));
}
$("#bt-fonte").addEventListener("click", () => { pref.fonte = !pref.fonte; aplicarPref(); avisar(pref.fonte ? "Letra grande ligada." : "Letra normal.", { icone: "a-large-small", ms: 2000 }); });
$("#bt-contraste").addEventListener("click", () => { pref.contraste = !pref.contraste; aplicarPref(); avisar(pref.contraste ? "Alto contraste ligado." : "Contraste normal.", { icone: "contrast", ms: 2000 }); });
$("#bt-sair").addEventListener("click", () => { api.sair(); S.usuario = null; pararFala(); location.hash = "#/entrar"; });

const anunciar = (t, urgente = false) => { const el = $(urgente ? "#anuncio-urgente" : "#anuncio"); el.textContent = ""; setTimeout(() => (el.textContent = t), 60); };

// ---------- Dados derivados ----------
const meuBairro = () => S.territorio?.bairros.find((b) => b.id === S.usuario?.bairro_id) ?? S.territorio?.bairros[0];
const estacaoDoBairro = (b) => S.territorio.estacoes.find((e) => e.id === b.estacao_id);
const riscoDo = (bairroId) => S.risco.find((r) => r.bairro_id === bairroId);
function nivelCm(b) {
  const r = riscoDo(b.id);
  if (r?.nivel_cm != null) return r.nivel_cm;
  return S.estacoes.find((e) => e.id === b.estacao_id)?.ultima_leitura?.nivel_cm ?? null;
}
function abrigoProximo(b) {
  const precisaAcess = (S.usuario?.vulnerabilidades ?? []).some((v) => ["pcd", "acamado", "idoso"].includes(v));
  const lista = S.territorio.abrigos.map((a) => ({ a, d: distanciaM(b, a) })).sort((x, y) => x.d - y.d);
  return (precisaAcess ? lista.find((x) => x.a.acessivel) : null) ?? lista[0];
}

// ---------- Inicialização ----------
async function iniciar() {
  injetarIcones();
  aplicarPref();
  const modo = await api.iniciar();
  if (modo === "demo") $("#faixa-sistema").innerHTML = `<span class="selo-demo" title="A API não respondeu. Tudo nesta tela é simulado e fica salvo só neste navegador.">Modo demonstração — dados simulados no navegador</span>`;
  main.addEventListener("click", (ev) => { if (ev.target.closest("[data-recarregar]")) location.reload(); });
  try { S.territorio = await api.territorio(); } catch (e) { render(main, telaErro(e)); return; }
  S.usuario = api.usuario();
  if (S.usuario) { try { S.usuario = await api.eu(); } catch (e) { if (e.status === 401) { api.sair(); S.usuario = null; } } }
  if (S.usuario?.papel === "defesa_civil") { api.sair(); S.usuario = null; }
  api.on(aoEvento);
  addEventListener("hashchange", rotear);
  await rotear();
  if ("serviceWorker" in navigator && location.protocol.startsWith("http")) navigator.serviceWorker.register("sw.js").catch(() => {});
  setInterval(() => { if (S.usuario && api.modo === "real") carregarRisco().then(atualizarAlerta).catch(() => {}); }, 60000);
}

async function carregarRisco() {
  S.risco = await api.riscoAtual();
  if (api.modo === "real" && S.risco.some((r) => r.nivel_cm == null)) S.estacoes = await api.estacoes().catch(() => S.estacoes);
}
async function carregarAlertas() {
  const b = meuBairro();
  S.alertas = await api.alertas(b.id).catch(() => S.alertas);
}

function aoEvento({ tipo, dados }) {
  if (tipo === "conexao") return mostrarOffline(dados.offline);
  if (!S.usuario) return;
  if (tipo === "risco") { S.risco = dados; atualizarAlerta(); S.mapa?.atualizarRisco(S.risco); atualizarListaBairros(); }
  if (tipo === "leitura") {
    const e = S.estacoes.find((x) => x.id === dados.estacao_id); if (e) e.ultima_leitura = dados;
  }
  if (tipo === "alerta" && dados.bairro_id === meuBairro().id) {
    S.alertas = [dados, ...S.alertas.filter((a) => a.id !== dados.id)];
    anunciar(`Novo alerta da Defesa Civil: ${dados.titulo}. ${dados.mensagem_completa}`, true);
    navigator.vibrate?.([400, 150, 400, 150, 600]);
    avisar(`Novo alerta da Defesa Civil: ${dados.titulo}`, { icone: "siren", ms: 6000 });
    renderAlertasDC(true);
  }
  if (tipo === "ocorrencia" && dados.usuario_id === S.usuario.id && S.rota === "relatos") telaRelatos();
}

function mostrarOffline(off) {
  const f = $("#faixa-offline");
  if (!off) { f.hidden = true; return; }
  const em = api.idadeCache("risco");
  f.innerHTML = `${ico("wifi-off")}<span>Sem internet. ${em ? `Mostrando o último estado salvo às ${hora(em)}.` : "Mostrando o último estado salvo."}</span>`;
  f.hidden = false;
}

// ---------- Roteador ----------
const ROTAS = { entrar: telaEntrar, cadastro: telaCadastro, alerta: telaAlerta, mapa: telaMapa, relatar: telaRelatar, relatos: telaRelatos };
const TITULOS = { entrar: "Entrar", cadastro: "Criar conta", alerta: "Meu alerta", mapa: "Mapa", relatar: "Relatar", relatos: "Meus relatos" };
async function rotear() {
  let rota = (location.hash.match(/^#\/(\w+)/) || [])[1] || (S.usuario ? "alerta" : "entrar");
  if (!ROTAS[rota]) rota = "alerta";
  if (!S.usuario && !["entrar", "cadastro"].includes(rota)) rota = "entrar";
  if (S.usuario && ["entrar", "cadastro"].includes(rota)) rota = "alerta";
  if (location.hash !== `#/${rota}`) history.replaceState(null, "", `#/${rota}`);
  const mudou = S.rota !== rota;
  S.rota = rota;
  if (rota !== "alerta") pararFala();
  if (S.mapa && rota !== "mapa") { S.mapa.mapa.remove(); S.mapa = null; }
  S.regua = rota === "alerta" ? S.regua : null;
  $("#nav").hidden = !S.usuario;
  $("#bt-sair").hidden = !S.usuario;
  $$("#nav a").forEach((a) => (a.dataset.rota === rota ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  document.title = `Margem — ${TITULOS[rota]}`;
  await ROTAS[rota]();
  if (mudou) { scrollTo({ top: 0 }); main.focus({ preventScroll: true }); }
}

function telaErro(e) {
  return html`<div class="pagina"><div class="estado">${ico("triangle-alert")}<strong>Não deu para carregar</strong><p>${e.message}</p><button class="btn" type="button" data-recarregar>${ico("refresh-cw")}Tentar de novo</button></div></div>`;
}

// ---------- Entrar ----------
function telaEntrar() {
  render(main, html`<section class="auth">
    <div class="auth-caixa">
      <div>
        <h1>O rio subiu? Você fica sabendo antes.</h1>
        <p class="lead">Alerta de enchente para quem mora na beira do Tietê: nível do rio, risco nas próximas 2 horas e o que fazer.</p>
      </div>
      <form class="form" id="f-entrar" novalidate>
        <div class="campo"><label for="email">E-mail</label><input class="entrada" id="email" name="email" type="email" autocomplete="username" inputmode="email" required></div>
        <div class="campo"><label for="senha">Senha</label><input class="entrada" id="senha" name="senha" type="password" autocomplete="current-password" required></div>
        <div id="erro-entrar" role="alert"></div>
        <button class="btn btn-primario btn-g" type="submit">Entrar</button>
        <p>Primeira vez? <a href="#/cadastro">Criar conta</a></p>
      </form>
      ${api.modo === "demo" ? html`<div class="demo-caixa">
        <span>Conta de demonstração (moradora do Jardim Pantanal): <span class="mono">maria@demo.margem.app</span> · <span class="mono">Margem@2026</span></span>
        <button class="btn btn-p" type="button" id="preencher-demo">${ico("user")}Usar conta de demonstração</button>
      </div>` : ""}
    </div>
  </section>`);
  $("#preencher-demo")?.addEventListener("click", () => { $("#email").value = "maria@demo.margem.app"; $("#senha").value = "Margem@2026"; $("#f-entrar button[type=submit]").focus(); });
  $("#f-entrar").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const bt = ev.submitter ?? $("#f-entrar button[type=submit]");
    const email = $("#email").value.trim(), senha = $("#senha").value;
    const err = $("#erro-entrar");
    if (!email || !senha) { err.innerHTML = `<p class="alerta-erro">${ico("triangle-alert")}Preencha e-mail e senha.</p>`; return; }
    bt.classList.add("carregando");
    try {
      const r = await api.login(email, senha);
      if (r.usuario.papel !== "cidadao") { api.sair(); throw new Error("Esta conta é da Defesa Civil. Use o console da Defesa Civil."); }
      S.usuario = r.usuario;
      location.hash = "#/alerta";
    } catch (e) {
      err.innerHTML = `<p class="alerta-erro">${ico("triangle-alert")}${esc(e.message)}</p>`;
    } finally { bt.classList.remove("carregando"); }
  });
}

// ---------- Cadastro ----------
function telaCadastro() {
  const op = S.territorio.bairros.map((b) => html`<option value="${b.id}">${b.nome}</option>`);
  const vul = Object.entries({
    idoso: ["Pessoa idosa (60 anos ou mais)", ""],
    pcd: ["Pessoa com deficiência ou mobilidade reduzida", "Usa cadeira de rodas, muleta, tem deficiência visual etc."],
    crianca: ["Criança pequena", "Até 6 anos"],
    gestante: ["Gestante", ""],
    acamado: ["Pessoa acamada", "Não consegue sair da cama sem ajuda"],
  }).map(([k, [t, d]]) => html`<label class="opcao"><input type="checkbox" name="vul" value="${k}"><span class="opcao-texto"><span>${t}</span>${d ? html`<small>${d}</small>` : ""}</span></label>`);
  render(main, html`<section class="auth"><div class="auth-caixa larga">
    <div><h1>Criar conta</h1><p class="lead">Leva 2 minutos. Com o seu bairro, o app mostra o rio mais perto de você.</p></div>
    <form class="form" id="f-cad" novalidate>
      <div class="secao-form primeira">
        <h2>Seus dados</h2>
        <div class="campo"><label for="c-nome">Nome</label><input class="entrada" id="c-nome" autocomplete="name" required></div>
        <div class="grade-2">
          <div class="campo"><label for="c-tel">Celular</label><input class="entrada" id="c-tel" type="tel" inputmode="tel" autocomplete="tel" placeholder="(11) 90000-0000" required><span class="dica">Para receber o SMS de alerta.</span></div>
          <div class="campo"><label for="c-bairro">Bairro</label><select class="entrada" id="c-bairro" required>${op}</select></div>
        </div>
      </div>
      <div class="secao-form">
        <h2>Acesso</h2>
        <div class="grade-2">
          <div class="campo"><label for="c-email">E-mail</label><input class="entrada" id="c-email" type="email" autocomplete="email" inputmode="email" required></div>
          <div class="campo"><label for="c-senha">Senha</label><input class="entrada" id="c-senha" type="password" autocomplete="new-password" minlength="8" required><span class="dica">Pelo menos 8 caracteres.</span></div>
        </div>
      </div>
      <fieldset class="secao-form">
        <legend class="sr-only">Quem mora com você</legend>
        <h2>Quem mora com você <span class="dica">(opcional)</span></h2>
        <p class="explica">Se alguém na casa precisa de mais tempo ou de ajuda para sair, marque abaixo. A Defesa Civil usa isso para chegar primeiro em quem mais precisa. Só a equipe da Defesa Civil vê esta informação, e você pode apagar quando quiser.</p>
        <div class="pilha">${vul}</div>
        <div class="campo"><label for="c-contato">Contato de emergência <span class="dica">(opcional)</span></label><input class="entrada" id="c-contato" placeholder="Nome e telefone de alguém de confiança"></div>
      </fieldset>
      <div class="secao-form">
        <h2>Seus dados e a LGPD</h2>
        <div class="lgpd">
          <p>Para o alerta funcionar, o Margem guarda:</p>
          <ul>
            <li>nome, celular, e-mail e bairro, para enviar alertas e falar com você numa emergência;</li>
            <li>quem mora com você (se marcou), que é dado sensível e só serve para priorizar o socorro;</li>
            <li>seus relatos e check-ins, vistos pela Defesa Civil.</li>
          </ul>
          <p>Não vendemos nem compartilhamos com empresas. Você pode pedir para ver, corrigir ou apagar seus dados a qualquer momento (Lei 13.709/2018).</p>
        </div>
        <label class="opcao"><input type="checkbox" id="c-lgpd" required><span class="opcao-texto"><span>Li e concordo com o uso dos meus dados para alertas e socorro em enchentes.</span></span></label>
      </div>
      <div id="erro-cad" role="alert"></div>
      <button class="btn btn-primario btn-g" type="submit">Criar conta</button>
      <p>Já tem conta? <a href="#/entrar">Entrar</a></p>
    </form>
  </div></section>`);
  $("#f-cad").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const err = $("#erro-cad");
    const v = (id) => $(id).value.trim();
    const faltando = [];
    $$("#f-cad [required]").forEach((el) => { const ok = el.type === "checkbox" ? el.checked : el.value.trim() && (!(el.minLength > 0) || el.value.length >= el.minLength); el.setAttribute("aria-invalid", String(!ok)); if (!ok) faltando.push(el); });
    if (faltando.length) {
      const lgpd = faltando.some((x) => x.id === "c-lgpd");
      err.innerHTML = `<p class="alerta-erro">${ico("triangle-alert")}${lgpd && faltando.length === 1 ? "Para criar a conta, marque que concorda com o uso dos dados." : "Confira os campos marcados em vermelho."}</p>`;
      faltando[0].focus(); return;
    }
    const bt = ev.submitter ?? $("#f-cad button[type=submit]");
    bt.classList.add("carregando");
    try {
      const s = await api.cadastro({ nome: v("#c-nome"), telefone: v("#c-tel"), bairro_id: v("#c-bairro"), email: v("#c-email"), senha: $("#c-senha").value,
        vulnerabilidades: $$("#f-cad input[name=vul]:checked").map((x) => x.value), contato_emergencia: v("#c-contato") || null, consentimento_lgpd: true });
      S.usuario = s.usuario;
      avisar("Conta criada. Bem-vinda ao Margem.", { icone: "check" });
      location.hash = "#/alerta";
    } catch (e) { err.innerHTML = `<p class="alerta-erro">${ico("triangle-alert")}${esc(e.message)}</p>`; }
    finally { bt.classList.remove("carregando"); }
  });
}

// ---------- Meu alerta ----------
async function telaAlerta() {
  const b = meuBairro();
  const e = estacaoDoBairro(b);
  if (!S.risco.length) render(main, html`<div class="pagina"><div class="esqueleto esq-placa"></div><div class="esqueleto esq-bloco"></div></div>`);
  await Promise.all([carregarRisco().catch(() => {}), carregarAlertas()]);
  if (S.rota !== "alerta") return;
  const ap = abrigoProximo(b);
  const ck = ultimoCheckin();
  render(main, html`<div class="pagina">
    <section class="placa" id="placa" aria-labelledby="placa-nivel">
      <div class="pl-onde">${ico("map-pin", "ico-s")}<span>${b.nome}</span><span aria-hidden="true">·</span><span id="pl-atualizado"></span></div>
      <h1 class="pl-nivel" id="placa-nivel"><span class="pl-degraus" aria-hidden="true"><i></i><i></i><i></i><i></i></span><span id="pl-rotulo"></span></h1>
    </section>
    <p class="resumo-nivel" id="resumo"></p>
    <div id="alertas-dc"></div>
    <div class="alerta-grade">
      <div class="col-regua">
        <section class="cartao" aria-labelledby="t-medidor">
          <div class="cartao-cab"><h2 id="t-medidor">Rio agora</h2><span class="rotulo-sec">${e.nome}</span></div>
          <div class="medidor">
            <div class="regua-caixa" id="regua"></div>
            <div class="leituras">
              <div class="leitura-grande"><div class="valor num" id="v-nivel">—</div><div class="det" id="v-tend"></div></div>
              <div class="leitura-mini"><b id="v-pct">—</b><span>da cota de alerta (${metros(e.cota_alerta_cm)})</span></div>
              <div class="leitura-mini"><b id="v-falta">—</b><span id="v-falta-r">até transbordar</span></div>
              <div class="leitura-mini"><b id="v-chuva">—</b><span>chuva agora</span></div>
            </div>
          </div>
          <div class="medidor-rodape"><span>Sensor <span class="mono">${e.id}</span></span><span id="v-hora" class="mono"></span></div>
        </section>
      </div>
      <div class="col-info">
        <section class="cartao chance" id="chance" aria-labelledby="t-chance">
          <div class="chance-matriz" id="matriz" aria-hidden="true">${raw("<i></i>".repeat(100))}</div>
          <div><h3 id="t-chance">Chance de transbordar nas próximas 2 horas</h3><div class="grande" id="ch-texto"></div><p id="ch-hora"></p></div>
        </section>
        <section class="cartao fazer" aria-labelledby="t-fazer"><h2 id="t-fazer">O que fazer agora</h2><ol id="fazer"></ol></section>
        <section class="cartao" aria-labelledby="t-ck">
          <div class="cartao-cab"><h2 id="t-ck">Avise como você está</h2></div>
          <div class="cartao-corpo checkin">
            <div class="btns">
              <button class="btn btn-seguro btn-g" id="bt-seguro" type="button">${ico("shield-check")}Estou seguro</button>
              <button class="btn btn-ajuda btn-g" id="bt-ajuda" type="button">${ico("life-buoy")}Preciso de ajuda</button>
            </div>
            <p class="ultimo" id="ck-ultimo" data-s="${ck?.status ?? ""}">${ck ? raw(textoCheckin(ck)) : "A Defesa Civil vê sua resposta na hora."}</p>
          </div>
        </section>
        <div class="linha-acoes">
          <button class="btn btn-tinta btn-bloco" id="bt-ouvir" type="button" aria-pressed="false">${ico("volume-2")}<span>Ouvir alerta</span></button>
        </div>
        <section class="cartao" aria-labelledby="t-apoio">
          <div class="cartao-cab"><h2 id="t-apoio">Ponto de apoio mais perto</h2></div>
          <div class="apoio">
            <span class="ap-ico">${ico("house")}</span>
            <div>
              <h3>${ap.a.nome.replace(" (simulado)", "")}</h3>
              <div class="det"><span>a ${distTexto(ap.d)} do centro do bairro</span><span>cabe ${ap.a.capacidade} pessoas</span>${ap.a.acessivel ? html`<span>${ico("accessibility", "ico-s")} acessível</span>` : html`<span>sem rampa</span>`}</div>
              <div class="acoes">
                <a class="btn btn-p" href="https://www.openstreetmap.org/directions?to=${ap.a.lat}%2C${ap.a.lng}" target="_blank" rel="noopener">${ico("navigation")}Como chegar</a>
                <a class="btn btn-p btn-fantasma" href="#/mapa">${ico("map")}Ver no mapa</a>
              </div>
            </div>
          </div>
          <div class="contatos" aria-label="Telefones de emergência">
            <a href="tel:199">${ico("phone", "ico-s")}Defesa Civil <b>199</b></a>
            <a href="tel:193">${ico("phone", "ico-s")}Bombeiros <b>193</b></a>
            <a href="tel:192">${ico("phone", "ico-s")}SAMU <b>192</b></a>
          </div>
        </section>
      </div>
    </div>
    <p class="rodape-app">Cotas e pontos de apoio são simulados para fins acadêmicos.</p>
  </div>`);
  S.regua = criarRegua($("#regua"), { cotaAlerta: e.cota_alerta_cm, cotaTransbordo: e.cota_transbordo_cm, titulo: `Régua do rio na estação ${e.nome}` });
  S.ultimoNivel = null;
  atualizarAlerta();
  renderAlertasDC(false);
  $("#bt-seguro").addEventListener("click", () => enviarCheckin("seguro"));
  $("#bt-ajuda").addEventListener("click", abrirAjuda);
  $("#bt-ouvir").addEventListener("click", alternarFala);
}

function atualizarAlerta() {
  if (S.rota !== "alerta" || !$("#placa")) return;
  const b = meuBairro(), e = estacaoDoBairro(b), r = riscoDo(b.id);
  if (!r) return;
  const n = indice(r.nivel), cm = nivelCm(b);
  const placa = $("#placa");
  if (S.ultimoNivel && S.ultimoNivel !== r.nivel) {
    placa.classList.remove("mudou"); void placa.offsetWidth; placa.classList.add("mudou");
    anunciar(`O risco no ${b.nome} mudou para ${ROTULO[r.nivel]}. ${RESUMO[r.nivel]}`, n >= 2);
    if (n >= 2) navigator.vibrate?.([300, 120, 300]);
  }
  placa.dataset.n = n;
  $("#chance").dataset.n = n;
  $("#pl-rotulo").textContent = ROTULO[r.nivel];
  $("#pl-atualizado").textContent = `atualizado ${ha(r.atualizado_em, api.agora().getTime())}`;
  $("#resumo").textContent = RESUMO[r.nivel];
  if (S.ultimoNivel !== r.nivel) $("#fazer").innerHTML = O_QUE_FAZER[r.nivel].map((t) => `<li>${esc(t)}</li>`).join("");
  S.ultimoNivel = r.nivel;
  if (cm != null) {
    S.regua?.atualizar(cm);
    $("#v-nivel").innerHTML = `${(cm / 100).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}<small>m</small>`;
    $("#v-pct").textContent = `${n0((cm / e.cota_alerta_cm) * 100)}%`;
    const falta = e.cota_transbordo_cm - cm;
    $("#v-falta").textContent = falta > 0 ? metros(falta) : "transbordou";
    $("#v-falta-r").textContent = falta > 0 ? "até transbordar" : `${metros(-falta)} acima da cota`;
  }
  const v1h = r.variacao_1h_cm;
  $("#v-tend").innerHTML = `<span class="tend" data-t="${r.tendencia}">${ico(r.tendencia === "subindo" ? "arrow-right" : r.tendencia === "descendo" ? "arrow-right" : "activity", "ico-s")}${TENDENCIA[r.tendencia] ?? r.tendencia}</span>${v1h != null ? `<span>${v1h > 0 ? "+" : ""}${n0(v1h)} cm em 1 h</span>` : ""}`;
  const seta = $("#v-tend .tend .ico"); if (seta) seta.style.transform = r.tendencia === "subindo" ? "rotate(-90deg)" : r.tendencia === "descendo" ? "rotate(90deg)" : "";
  const chuva = r.chuva_mm_h ?? S.estacoes.find((x) => x.id === e.id)?.ultima_leitura?.chuva_mm_h;
  $("#v-chuva").textContent = chuva != null ? `${n1(chuva)} mm/h` : "—";
  $("#v-hora").textContent = `leitura ${hora(r.atualizado_em)}`;
  const c = chanceSimples(r.prob);
  $$("#matriz i").forEach((el, i) => el.classList.toggle("on", i < c.p));
  $("#ch-texto").textContent = `${c.palavra[0].toUpperCase()}${c.palavra.slice(1)}: ${c.frase}`;
  const ate = new Date(api.agora().getTime() + 2 * 3600e3);
  $("#ch-hora").textContent = `Previsão do modelo até as ${hora(ate)}, com base no nível, na chuva e na umidade do solo.`;
}

function renderAlertasDC(novo) {
  const caixa = $("#alertas-dc"); if (!caixa) return;
  const a = S.alertas[0];
  if (!a) { caixa.innerHTML = ""; return; }
  caixa.innerHTML = String(html`<section class="alerta-dc" data-n="${indice(a.nivel)}" ${raw(novo ? "" : 'data-calmo=""')} aria-labelledby="ad-t">
    <div class="ad-cab">${ico("siren")}<span>Alerta da Defesa Civil</span><span aria-hidden="true">·</span><span class="mono">${hora(a.emitido_em)}</span>${etiquetaNivel(a.nivel)}</div>
    <h2 id="ad-t">${a.titulo}</h2>
    <p>${a.mensagem_completa}</p>
    <div class="ad-acoes"><button class="btn btn-p btn-tinta" type="button" id="ad-ouvir">${ico("volume-2")}Ouvir este alerta</button><span class="ad-validade">válido até ${hora(a.valido_ate)}</span></div>
  </section>`);
  $("#ad-ouvir").addEventListener("click", () => falar(`${a.titulo}. ${a.mensagem_completa}`));
}

// ---------- Check-in ----------
const chaveCk = () => `margem:ultimo-checkin:${S.usuario?.id}`;
function ultimoCheckin() { try { return JSON.parse(localStorage.getItem(chaveCk())); } catch { return null; } }
function textoCheckin(ck) {
  return String(html`${ico(ck.status === "seguro" ? "shield-check" : "life-buoy")}<span>${ck.status === "seguro" ? "Você avisou que está seguro" : "Você pediu ajuda"} às ${hora(ck.criado_em)}.</span>`);
}
async function enviarCheckin(status, obs = "") {
  const bt = status === "seguro" ? $("#bt-seguro") : $("#bt-ajuda");
  bt?.classList.add("carregando");
  try {
    const ck = await api.checkin(status, obs);
    localStorage.setItem(chaveCk(), JSON.stringify(ck));
    const el = $("#ck-ultimo");
    if (el) { el.dataset.s = status; el.innerHTML = textoCheckin(ck); el.classList.remove("atualizou"); void el.offsetWidth; el.classList.add("atualizou"); }
    avisar(status === "seguro" ? "Obrigado. A Defesa Civil sabe que você está seguro." : "Pedido de ajuda enviado. A Defesa Civil já está vendo.", { icone: status === "seguro" ? "shield-check" : "life-buoy", ms: 5000 });
    anunciar(status === "seguro" ? "Check-in enviado: você está seguro." : "Pedido de ajuda enviado à Defesa Civil.");
  } catch (e) { avisar(e.message, { icone: "triangle-alert" }); }
  finally { bt?.classList.remove("carregando"); }
}
function abrirAjuda() {
  const d = $("#dlg-ajuda");
  $("#ajuda-obs").value = "";
  d.showModal();
  d.onclose = () => { if (d.returnValue === "enviar") enviarCheckin("preciso_ajuda", $("#ajuda-obs").value.trim()); };
}

// ---------- Voz (Web Speech API, pt-BR) ----------
function vozPt() {
  const vs = speechSynthesis.getVoices();
  return vs.find((v) => v.lang === "pt-BR" && /natural|online|google/i.test(v.name)) ?? vs.find((v) => v.lang === "pt-BR") ?? vs.find((v) => v.lang?.startsWith("pt"));
}
function textoFalado() {
  const b = meuBairro(), r = riscoDo(b.id), cm = nivelCm(b);
  if (!r) return "Ainda não há leitura do rio.";
  const m = Math.floor(cm / 100), c = Math.round(cm % 100);
  const ch = chanceSimples(r.prob);
  const a = S.alertas[0];
  return `${a ? `Alerta da Defesa Civil: ${a.mensagem_completa} ` : ""}Risco no ${b.nome}: ${ROTULO[r.nivel]}. ${RESUMO[r.nivel]} O rio está em ${m} metro${m === 1 ? "" : "s"} e ${c} centímetros. A chance de transbordar nas próximas duas horas é ${ch.palavra}: ${ch.p} em cada 100. O que fazer agora: ${O_QUE_FAZER[r.nivel].join(" ").replace(/·/g, ",")}`;
}
function falar(texto) {
  if (!("speechSynthesis" in window)) { avisar("Este navegador não tem leitura em voz.", { icone: "volume-2" }); return; }
  pararFala();
  const u = new SpeechSynthesisUtterance(texto);
  u.lang = "pt-BR"; u.rate = 0.92; const v = vozPt(); if (v) u.voice = v;
  u.onend = u.onerror = () => marcarFala(false);
  speechSynthesis.speak(u);
  marcarFala(true);
}
function marcarFala(v) {
  S.falando = v;
  const bt = $("#bt-ouvir"); if (!bt) return;
  bt.setAttribute("aria-pressed", String(v));
  bt.querySelector("span").textContent = v ? "Parar leitura" : "Ouvir alerta";
}
function pararFala() { if ("speechSynthesis" in window) speechSynthesis.cancel(); marcarFala(false); }
function alternarFala() { if (S.falando) pararFala(); else falar(textoFalado()); }

// ---------- Mapa ----------
async function telaMapa() {
  render(main, html`<div class="pagina mapa-pagina">
    <div><h1>Mapa</h1><p class="sub">Estações que medem o rio, risco por bairro e pontos de apoio.</p></div>
    <div class="filtros-mapa" role="group" aria-label="Camadas do mapa">
      <button class="chip" type="button" aria-pressed="true" data-camada="bairros">${ico("map-pin", "ico-s")}Bairros</button>
      <button class="chip" type="button" aria-pressed="true" data-camada="estacoes">${ico("radio-tower", "ico-s")}Estações</button>
      <button class="chip" type="button" aria-pressed="true" data-camada="abrigos">${ico("house", "ico-s")}Pontos de apoio</button>
    </div>
    <div class="mapa-caixa" id="mapa" aria-label="Mapa da várzea do Tietê com bairros, estações e pontos de apoio"></div>
    <div class="legenda" aria-label="Legenda">${["observacao", "atencao", "alerta", "alerta_maximo"].map((n) => etiquetaNivel(n))}<span>${ico("house", "ico-s")} ponto de apoio</span></div>
    <section class="cartao" aria-labelledby="t-lb"><div class="cartao-cab"><h2 id="t-lb">Risco por bairro</h2></div><ul class="lista-bairros" id="lista-bairros"></ul></section>
  </div>`);
  if (!S.risco.length) await carregarRisco().catch(() => {});
  await esperarLeaflet();
  if (S.rota !== "mapa") return;
  S.mapa = criarMapa($("#mapa"), S.territorio, { tema: "claro" });
  const b = meuBairro();
  S.mapa?.focar(b.lat, b.lng, innerWidth < 600 ? 13 : 14);
  S.mapa?.atualizarRisco(S.risco);
  atualizarListaBairros();
  $$(".filtros-mapa .chip").forEach((c) => c.addEventListener("click", () => {
    const v = c.getAttribute("aria-pressed") !== "true"; c.setAttribute("aria-pressed", String(v)); S.mapa?.alternar(c.dataset.camada, v);
  }));
}
function atualizarListaBairros() {
  const ul = $("#lista-bairros"); if (!ul) return;
  const meu = meuBairro().id;
  ul.innerHTML = S.territorio.bairros.map((b) => {
    const r = riscoDo(b.id); const cm = nivelCm(b); const e = estacaoDoBairro(b);
    return String(html`<li><div><div class="lb-nome">${b.nome}${b.id === meu ? " (seu bairro)" : ""}</div><div class="lb-det">rio ${cm != null ? metros(cm) : "—"} · alerta em ${metros(e.cota_alerta_cm)} · chance 2 h: ${r ? Math.round(r.prob * 100) : "—"} em 100</div></div>${r ? etiquetaNivel(r.nivel) : ""}</li>`);
  }).join("");
}
function esperarLeaflet() {
  return new Promise((ok) => { if (window.L) return ok(); const t = setInterval(() => { if (window.L) { clearInterval(t); ok(); } }, 50); setTimeout(() => { clearInterval(t); ok(); }, 4000); });
}

// ---------- Relatar ----------
const AGENTES = {
  triagem: ["Agente de triagem", "bot", "Classifica o relato e procura pessoas vulneráveis"],
  protocolos: ["Agente de protocolos", "book-open", "Busca orientações na base da Defesa Civil"],
  prioridade: ["Agente de prioridade", "gauge", "Calcula a prioridade na fila"],
  resposta: ["Resposta ao morador", "send", "Escreve o que você deve fazer agora"],
  comunicador: ["Agente comunicador", "megaphone", "Redige a mensagem"],
};
const agente = (nome) => AGENTES[nome] ?? [nome.charAt(0).toUpperCase() + nome.slice(1), "cpu", ""];

function telaRelatar() {
  const b = meuBairro();
  const op = S.territorio.bairros.map((x) => html`<option value="${x.id}" ${raw(x.id === b.id ? "selected" : "")}>${x.nome}</option>`);
  const sug = ["A água está entrando em casa", "A rua está alagada", "Tem gente ilhada", "Apareceu rachadura no muro", "Estamos sem luz e tem fio caído"];
  render(main, html`<div class="pagina">
    <h1>Relatar o que está acontecendo</h1>
    <p class="sub">Escreva do seu jeito. A inteligência artificial lê o relato, procura as orientações certas e coloca seu pedido na fila da Defesa Civil.</p>
    <div class="relatar">
      <form class="form cartao cartao-corpo" id="f-relato" novalidate>
        <div class="campo">
          <label for="r-texto">O que está acontecendo?</label>
          <textarea class="entrada" id="r-texto" maxlength="1000" rows="6" placeholder="Ex.: a água está entrando em casa e minha mãe usa cadeira de rodas" aria-describedby="r-cont"></textarea>
          <div class="contador-txt" id="r-cont">0/1000</div>
        </div>
        <div class="campo"><span class="rotulo">Começar com</span><div class="sugestoes">${sug.map((t) => html`<button type="button" class="chip" data-sug="${t}">${t}</button>`)}</div></div>
        <div class="campo"><label for="r-bairro">Bairro</label><select class="entrada" id="r-bairro">${op}</select></div>
        <div class="campo">
          <button type="button" class="btn btn-p" id="r-geo" aria-pressed="false">${ico("map-pin")}Enviar minha localização</button>
          <span class="dica" id="r-geo-st">Opcional. Ajuda a equipe a chegar mais rápido.</span>
        </div>
        <div id="r-erro" role="alert"></div>
        <button class="btn btn-primario btn-g" type="submit">${ico("send")}Enviar relato</button>
      </form>
      <section id="r-result" aria-live="polite">
        <div class="cartao estado">${ico("bot")}<strong>Como a IA trata o seu relato</strong>
          <p>Quatro agentes trabalham em sequência: triagem, protocolos, prioridade e resposta. Você vê cada passo aqui depois de enviar.</p></div>
      </section>
    </div>
  </div>`);
  const tx = $("#r-texto"), cont = $("#r-cont");
  tx.addEventListener("input", () => (cont.textContent = `${tx.value.length}/1000`));
  $$("[data-sug]").forEach((c) => c.addEventListener("click", () => { tx.value = `${c.dataset.sug}${tx.value ? ". " + tx.value : " "}`; tx.focus(); tx.dispatchEvent(new Event("input")); }));
  let geo = null;
  $("#r-geo").addEventListener("click", () => {
    const st = $("#r-geo-st");
    if (!navigator.geolocation) { st.textContent = "Este aparelho não informa a localização."; return; }
    st.textContent = "Pedindo a localização…";
    navigator.geolocation.getCurrentPosition((p) => { geo = { lat: p.coords.latitude, lng: p.coords.longitude }; st.textContent = "Localização anexada ao relato."; $("#r-geo").setAttribute("aria-pressed", "true"); },
      () => { st.textContent = "Sem permissão de localização. Tudo bem, o bairro já ajuda."; }, { timeout: 8000 });
  });
  $("#f-relato").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const texto = tx.value.trim(), err = $("#r-erro");
    if (texto.length < 10) { err.innerHTML = `<p class="alerta-erro">${ico("triangle-alert")}Conte um pouco mais (pelo menos 10 letras).</p>`; tx.setAttribute("aria-invalid", "true"); tx.focus(); return; }
    tx.removeAttribute("aria-invalid"); err.innerHTML = "";
    const bt = ev.submitter ?? $("#f-relato button[type=submit]");
    bt.classList.add("carregando");
    mostrarRastroPendente();
    try {
      const oc = await api.criarOcorrencia({ texto, bairro_id: $("#r-bairro").value, ...(geo ?? {}) });
      await animarRastro(oc);
      tx.value = ""; cont.textContent = "0/1000";
    } catch (e) {
      $("#r-result").innerHTML = `<div class="cartao estado">${ico("triangle-alert")}<strong>O relato não foi enviado</strong><p>${esc(e.message)}</p></div>`;
    } finally { bt.classList.remove("carregando"); }
  });
}

function mostrarRastroPendente() {
  const passos = ["triagem", "protocolos", "prioridade", "resposta"];
  $("#r-result").innerHTML = String(html`<div class="cartao cartao-corpo"><h2 class="tit-rastro">Analisando seu relato</h2>
    <ol class="rastro" id="rastro">${passos.map((p, i) => { const [n, ic, d] = agente(p); return html`<li class="${raw(i === 0 ? "ativo" : "")}" data-ag="${p}"><span class="r-ico">${ico(i === 0 ? "refresh-cw" : ic, "ico-s")}</span><div><div class="r-cab"><span class="r-nome">${n}</span><span class="r-ms"></span></div><div class="r-saida">${d}</div></div></li>`; })}</ol></div>`);
}

async function animarRastro(oc) {
  const t = oc.triagem;
  const lista = $("#rastro");
  const passos = t.rastro ?? [];
  lista.innerHTML = String(html`${passos.map((p) => { const [n, , d] = agente(p.agente); return html`<li data-ag="${p.agente}"><span class="r-ico">${ico(agente(p.agente)[1], "ico-s")}</span><div><div class="r-cab"><span class="r-nome">${n}</span><span class="r-ms"></span></div><div class="r-saida">${d}</div></div></li>`; })}`);
  const itens = $$("li[data-ag]", lista);
  const pausa = reduzMovimento() ? 0 : 520;
  for (let i = 0; i < itens.length; i++) {
    const li = itens[i], p = passos[i];
    li.classList.add("ativo");
    li.querySelector(".r-ico").innerHTML = String(ico("refresh-cw", "ico-s"));
    await new Promise((r) => setTimeout(r, pausa));
    li.classList.remove("ativo"); li.classList.add("feito");
    li.querySelector(".r-ico").innerHTML = String(ico("check", "ico-s"));
    li.querySelector(".r-ms").textContent = `${p.ms} ms`;
    let saida = String(html`${p.saida}`);
    if (p.agente === "protocolos" && t.fontes?.length) saida += String(html`<ul class="r-fontes">${t.fontes.map((f) => html`<li><span class="mono">${f.doc}</span> · <b>${f.titulo}</b><br>${f.trecho}</li>`)}</ul>`);
    li.querySelector(".r-saida").innerHTML = saida;
  }
  await new Promise((r) => setTimeout(r, pausa / 2));
  const res = document.createElement("div");
  res.className = "resultado";
  res.innerHTML = String(html`
    <div class="orientacao"><span class="rotulo-sec">O que fazer agora</span><p>${t.orientacao}</p></div>
    <div class="cartao">
      <div class="cartao-cab"><h2>Relato <span class="mono">${oc.id}</span> na fila</h2>${etiquetaStatus(oc.status)}</div>
      <div class="cartao-corpo pilha">
        <p><b>${CATEGORIA[t.categoria] ?? t.categoria}</b> — ${t.resumo}</p>
        ${t.vulneraveis?.length ? html`<div class="tags">${t.vulneraveis.map((v) => html`<span class="selo">${ico("heart-pulse")}${VULNERAVEL[v] ?? v}</span>`)}</div>` : ""}
      </div>
      <div class="ficha">
        <div><span>Gravidade</span><b>${t.gravidade}<small>/5</small></b><span class="escala5" aria-hidden="true">${raw([1, 2, 3, 4, 5].map((k) => `<i class="${k <= t.gravidade ? "on" : ""}"></i>`).join(""))}</span></div>
        <div><span>Prioridade</span><b>${t.prioridade}<small>/100</small></b></div>
        <div><span>Confiança</span><b>${Math.round((t.confianca ?? 0) * 100)}%</b><span class="mono">${t.modo}</span></div>
      </div>
    </div>
    <a class="btn" href="#/relatos">${ico("list-checks")}Acompanhar em Meus relatos</a>`);
  lista.closest(".cartao").after(res);
  lista.closest(".cartao").querySelector("h2").textContent = "Como a IA tratou seu relato";
  res.querySelector(".orientacao").focus?.();
  anunciar(`Relato enviado. ${t.orientacao}`);
}

const etiquetaStatus = (s) => html`<span class="selo"><span class="ponto" data-st="${s}"></span>${STATUS_OC[s] ?? s}</span>`;

// ---------- Meus relatos ----------
async function telaRelatos() {
  if (!$(".relatos")) render(main, html`<div class="pagina"><h1>Meus relatos</h1><p class="sub">Acompanhe o que a Defesa Civil está fazendo com cada relato.</p><div class="esqueleto esq-bloco"></div></div>`);
  let lista;
  try { lista = await api.ocorrencias(); } catch (e) { render(main, telaErro(e)); return; }
  if (S.rota !== "relatos") return;
  const passo = { aberta: 1, em_atendimento: 2, resolvida: 3 };
  render(main, html`<div class="pagina">
    <h1>Meus relatos</h1><p class="sub">Acompanhe o que a Defesa Civil está fazendo com cada relato.</p>
    ${lista.length ? html`<ul class="relatos">${lista.map((o) => html`<li class="cartao relato">
      <div class="rl-cab"><span class="rl-id">${o.id} · ${ha(o.criado_em, api.agora().getTime())}</span>${etiquetaStatus(o.status)}</div>
      <div class="rl-resumo">${o.triagem.resumo}</div>
      <div class="rl-texto">“${o.texto}”</div>
      <div class="passos" aria-label="Andamento: ${STATUS_OC[o.status]}"><span class="ok">Recebido</span><span class="${raw(passo[o.status] >= 2 ? "ok" : "")}">Em atendimento</span><span class="${raw(passo[o.status] >= 3 ? "ok" : "")}">Resolvido</span></div>
    </li>`)}</ul>` : html`<div class="cartao estado">${ico("inbox")}<strong>Nenhum relato ainda</strong><p>Quando você relatar algo, ele aparece aqui com o andamento.</p><a class="btn btn-primario" href="#/relatar">${ico("square-pen")}Fazer um relato</a></div>`}
  </div>`);
}

iniciar();
