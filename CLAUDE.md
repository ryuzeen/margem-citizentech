# Margem — Global Solution 2026/2 FIAP (CitizenTech)

Alerta comunitário de enchentes (várzea do Tietê, zona leste de SP). 4 áreas avaliadas + vídeo pitch.
Grupo: Italo de Souza (551500), Victor Montenegro Borges (98708), Matheus Morete Espinoso (552428),
Octávio Hernandez (97894), Rafael Perussi Caczan (93092). Entrega: 19/11/2026 23h55.

## Regras que não podem ser quebradas
- Só tecnologias vistas até a fase 7 (ver docs/DECISOES.md). Front = HTML/CSS/JS puro, backend = Python.
- Cada área precisa rodar seguindo **só o README**. `python iniciar.py` sobe tudo sem Docker.
- Commits só como ryuzeen, sem menção a Claude/IA de autoria. Repo público ryuzeen/margem-citizentech.
- Dados simulados sempre rotulados como simulados. Nada de inventar entrevista/validação.

## Comandos
- Instalar/rodar: `python iniciar.py`
- Testes: `.venv/Scripts/python -m pytest` (e2e: `-m e2e`)
- Lint: `.venv/Scripts/python -m ruff check .`
- Modo completo: `docker compose --profile completo up -d`

## Docs
Consultar `docs/` antes de mudanças grandes: CONTRATOS.md (interfaces entre áreas), DESIGN.md,
DECISOES.md, ROADMAP.md, ERROS-CORRIGIDOS.md.
