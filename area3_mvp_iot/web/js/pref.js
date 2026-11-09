// Preferências de acessibilidade aplicadas antes da pintura (evita piscar). Arquivo separado (e não inline)
// porque a CSP da API só permite script-src 'self'.
try {
  var p = JSON.parse(localStorage.getItem("margem:pref") || "{}");
  if (p.fonte) document.documentElement.dataset.fonte = "grande";
  if (p.contraste) document.documentElement.dataset.contraste = "alto";
} catch (e) { /* sem localStorage */ }
