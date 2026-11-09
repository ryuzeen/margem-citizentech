// Cópia de config/territorio.json para o modo demonstração (o front é servido só com web/).
// Território acadêmico: bairros reais, coordenadas aproximadas; população, cotas e abrigos SIMULADOS.
export const TERRITORIO = {
  "_aviso": "Território acadêmico. Bairros reais da várzea do Rio Tietê (zona leste de SP) com coordenadas aproximadas; população, cotas, abrigos e cadastros são SIMULADOS.",
  "cidade": "São Paulo - SP",
  "rio": "Rio Tietê",
  "centro": { "lat": -23.4905, "lng": -46.4180, "zoom": 14 },
  "bairros": [
    { "id": "jardim-pantanal", "nome": "Jardim Pantanal", "lat": -23.4927, "lng": -46.4290, "populacao_estimada": 42000, "domicilios_area_risco": 3100, "estacao_id": "EST-PANTANAL-01" },
    { "id": "vila-itaim", "nome": "Vila Itaim", "lat": -23.4962, "lng": -46.4128, "populacao_estimada": 28000, "domicilios_area_risco": 1900, "estacao_id": "EST-ITAIM-01" },
    { "id": "jardim-romano", "nome": "Jardim Romano", "lat": -23.4868, "lng": -46.4006, "populacao_estimada": 31000, "domicilios_area_risco": 2400, "estacao_id": "EST-ROMANO-01" },
    { "id": "jardim-helena", "nome": "Jardim Helena", "lat": -23.4836, "lng": -46.4185, "populacao_estimada": 37000, "domicilios_area_risco": 1600, "estacao_id": "EST-HELENA-01" }
  ],
  "estacoes": [
    { "id": "EST-PANTANAL-01", "bairro_id": "jardim-pantanal", "nome": "Margem do Tietê - Pantanal", "lat": -23.4901, "lng": -46.4302, "altura_instalacao_cm": 520, "cota_alerta_cm": 260, "cota_transbordo_cm": 340, "nivel_base_cm": 110 },
    { "id": "EST-ITAIM-01", "bairro_id": "vila-itaim", "nome": "Córrego Itaim", "lat": -23.4949, "lng": -46.4141, "altura_instalacao_cm": 420, "cota_alerta_cm": 190, "cota_transbordo_cm": 250, "nivel_base_cm": 70 },
    { "id": "EST-ROMANO-01", "bairro_id": "jardim-romano", "nome": "Várzea - Romano", "lat": -23.4851, "lng": -46.4021, "altura_instalacao_cm": 480, "cota_alerta_cm": 230, "cota_transbordo_cm": 300, "nivel_base_cm": 95 },
    { "id": "EST-HELENA-01", "bairro_id": "jardim-helena", "nome": "Margem - Helena", "lat": -23.4818, "lng": -46.4199, "altura_instalacao_cm": 500, "cota_alerta_cm": 250, "cota_transbordo_cm": 320, "nivel_base_cm": 100 }
  ],
  "abrigos": [
    { "id": "ABR-01", "nome": "Ponto de apoio - Escola Municipal (simulado)", "bairro_id": "jardim-pantanal", "lat": -23.4978, "lng": -46.4262, "capacidade": 180, "acessivel": true },
    { "id": "ABR-02", "nome": "Ponto de apoio - Centro Esportivo (simulado)", "bairro_id": "vila-itaim", "lat": -23.5004, "lng": -46.4109, "capacidade": 250, "acessivel": true },
    { "id": "ABR-03", "nome": "Ponto de apoio - Igreja comunitária (simulado)", "bairro_id": "jardim-romano", "lat": -23.4915, "lng": -46.3990, "capacidade": 120, "acessivel": false },
    { "id": "ABR-04", "nome": "Ponto de apoio - UBS / salão (simulado)", "bairro_id": "jardim-helena", "lat": -23.4880, "lng": -46.4160, "capacidade": 90, "acessivel": true }
  ],
  "contatos": { "defesa_civil": "199", "bombeiros": "193", "samu": "192" }
}
;
