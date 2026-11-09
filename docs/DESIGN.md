# Direção visual — Margem

## Ideia
O motivo visual é a **régua linimétrica**, aquela régua pintada que fica na margem do rio para medir o nível.
Ela vira o medidor de risco do app (traços, cota de alerta marcada, "lâmina d'água" subindo). Ao fundo, de leve,
curvas de nível topográficas. O tom é **cívico e confiável**, como sinalização pública bem feita, e não de startup.

O público é morador de várzea: idosos, celulares simples, sol na tela, pressa e medo. Por isso a legibilidade
vem antes da estética, e a estética vem da tipografia, do grid e de dados reais na tela.

## Tipografia (arquivos em `web/vendor/fonts/`, licença OFL)
- **Atkinson Hyperlegible Next**: texto e UI. Foi feita pelo Braille Institute para baixa visão, e isso entra no pitch.
- **Archivo** (largura normal, tracking negativo): títulos e números grandes, em duas cores (branco + cinza) nos títulos de seção.
- **IBM Plex Mono**: leituras de sensor, horários, IDs.
- Tamanho base de 17px no app do cidadão e 15px no console. A escala usa razão de 1.25. Números usam `font-variant-numeric: tabular-nums`.

## Cor (redesign de nov/2026: família escura monocromática nas três telas)
Fonte única: `web/css/tokens.css`. Landing, app do morador e console usam a mesma família.

| token | uso | valor |
|---|---|---|
| `--papel` | fundo | `#0B0B0C` |
| `--superficie` / `--superficie-2` | camadas de grafite | `#141416` / `#1B1B1E` |
| `--cartao` | cartões (gradiente sutil) | `#19191C → #111113` |
| `--tinta` / `--tinta-2` / `--tinta-3` | texto | `#F4F4F5` / `#A1A1AA` / `#8A8A93` |
| `--linha` / `--linha-forte` | linhas finas | branco 8% / 16% |
| `--agua` | água, mapa | `#4FA3BF` |
| `--risco-0..3` | Observação, Atenção, Alerta, Alerta máximo | `#3D8B5F` `#C98F0A` `#E0631C` `#C21F3A` |

Botão primário = pílula branca com texto preto; secundário = pílula escura com linha fina. A única cor da
interface é o risco (e a água). O modo **alto contraste** do app volta para preto no branco (`app.css`).
O risco **nunca** depende só da cor: sempre tem rótulo e ícone/posição na régua.

## Duas experiências
1. **App do morador** (mobile-first, PWA, funciona offline com o último estado em cache). Telas: entrar/cadastro,
   meu alerta (régua + o que fazer + botões grandes "Estou seguro" / "Preciso de ajuda" + ouvir alerta),
   mapa (estações, áreas, pontos de apoio), relatar ocorrência (com o rastro dos agentes visível).
2. **Console da Defesa Civil** (desktop, tema escuro, denso). Telas: fila priorizada, check-ins, emitir alerta,
   dashboard analítico, estações IoT + cenário de simulação.

Mais uma landing pública curta (o que é, como funciona, ODS), que serve de porta de entrada no pitch.

## Proibido (cara de "vibecodado")
Gradiente roxo/azul, glassmorphism, emoji como ícone, cartões genéricos com sombra grande, hero do tipo
"Revolucionando o futuro", texto placeholder, ícones de pacote misturados, animação em tudo.
Feedback do Rafa (nov/2026): nada de selo com borda tracejada + bolinha colorida; nada de rótulo em fonte mono
CAIXA ALTA espaçada (mono só para dado de sensor, ID e horário); card de bento não pode sobrar vazio; fundo de
seção é sempre largura total (testar em 1920 e 2560 px).
Use ícones SVG de um conjunto só (Lucide, subset vendorizado), raio 8/12/20px (pílula nos botões), sem sombra preta (luz no topo do cartão) e borda fina,
e **dados e texto reais** em todas as telas.

## Movimento
Pouco e com propósito: a água da régua sobe e desce (transform), entrada de alerta novo, feedback de toque.
Tudo respeita `prefers-reduced-motion`.

## Acessibilidade
Alvos de toque ≥ 48px, foco visível, `aria-live` para alerta novo, leitura em voz (Web Speech API, pt-BR),
alternância de fonte grande e alto contraste, navegação 100% por teclado, `lang="pt-BR"`.
