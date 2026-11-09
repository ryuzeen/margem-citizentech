# Direção visual — Margem

## Ideia
O motivo visual é a **régua linimétrica**, aquela régua pintada que fica na margem do rio para medir o nível.
Ela vira o medidor de risco do app (traços, cota de alerta marcada, "lâmina d'água" subindo). Ao fundo, de leve,
curvas de nível topográficas. O tom é **cívico e confiável**, como sinalização pública bem feita, e não de startup.

O público é morador de várzea: idosos, celulares simples, sol na tela, pressa e medo. Por isso a legibilidade
vem antes da estética, e a estética vem da tipografia, do grid e de dados reais na tela.

## Tipografia (arquivos em `web/vendor/fonts/`, licença OFL)
- **Atkinson Hyperlegible Next**: texto e UI. Foi feita pelo Braille Institute para baixa visão, e isso entra no pitch.
- **Archivo** (largura expandida/semicondensada): títulos e números grandes, com cara de placa.
- **IBM Plex Mono**: leituras de sensor, horários, IDs.
- Tamanho base de 17px no app do cidadão e 15px no console. A escala usa razão de 1.25. Números usam `font-variant-numeric: tabular-nums`.

## Cor
| token | uso | valor |
|---|---|---|
| `--tinta` | texto/fundo escuro | `#0E1A24` |
| `--papel` | fundo do app do cidadão | `#F4F1EA` |
| `--superficie` | cartões | `#FFFFFF` |
| `--linha` | bordas | `#D9D3C7` |
| `--agua` | marca, links, água | `#1F6F8B` |
| `--agua-clara` | preenchimento da água | `#CFE6EC` |
| `--risco-0` | Observação | `#3D8B5F` |
| `--risco-1` | Atenção | `#C98F0A` |
| `--risco-2` | Alerta | `#E0631C` |
| `--risco-3` | Alerta máximo | `#C21F3A` |
| console Defesa Civil (escuro) | fundo / painel / texto | `#0B141B` / `#121E27` / `#E8E4DA` |

O contraste mínimo é WCAG AA, e AAA no texto do alerta. O risco **nunca** depende só da cor: sempre tem rótulo e
ícone/posição na régua.

## Duas experiências
1. **App do morador** (mobile-first, PWA, funciona offline com o último estado em cache). Telas: entrar/cadastro,
   meu alerta (régua + o que fazer + botões grandes "Estou seguro" / "Preciso de ajuda" + ouvir alerta),
   mapa (estações, áreas, pontos de apoio), relatar ocorrência (com o rastro dos agentes visível).
2. **Console da Defesa Civil** (desktop, tema escuro, denso). Telas: fila priorizada, check-ins, emitir alerta,
   dashboard analítico, estações IoT + cenário de simulação.

Mais uma landing pública curta (o que é, como funciona, ODS), que serve de porta de entrada no pitch.

## Proibido (cara de "vibecodado")
Gradiente roxo/azul, glassmorphism, emoji como ícone, cartões genéricos com sombra grande, hero do tipo
"Revolucionando o futuro", texto placeholder, ícones de pacote misturados, animação em tudo, cantos de 24px em tudo.
Use ícones SVG de um conjunto só (Lucide, subset vendorizado), raio de 6–10px, sombra quase nula com borda fina,
e **dados e texto reais** em todas as telas.

## Movimento
Pouco e com propósito: a água da régua sobe e desce (transform), entrada de alerta novo, feedback de toque.
Tudo respeita `prefers-reduced-motion`.

## Acessibilidade
Alvos de toque ≥ 48px, foco visível, `aria-live` para alerta novo, leitura em voz (Web Speech API, pt-BR),
alternância de fonte grande e alto contraste, navegação 100% por teclado, `lang="pt-BR"`.
