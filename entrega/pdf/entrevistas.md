# Entrevistas com o público

<!--
Uma linha por entrevista na tabela; depois, o que mudou no projeto. Para regerar o PDF, na raiz do projeto:
    .venv/Scripts/python entrega/pdf/gerar_pdf.py
Só primeiro nome ou iniciais (LGPD).
-->

| Quem (perfil) | Onde / quando | O que disse | O que mudou no Margem |
|---|---|---|---|
| Dona Cida, 71 anos, mora sozinha no Jardim Pantanal | conversa por telefone, 10/11 | "Quando a sirene toca, a água já está no portão. E aquele aplicativo da prefeitura tem letra miúda, eu não enxergo." | letra grande e alto contraste com um toque no topo do app; botão "Ouvir alerta" lê o aviso em voz alta |
| Joice, 34 anos, mãe de um menino cadeirante, Vila Itaim | conversa presencial na associação de moradores, 11/11 | "Eu preciso sair antes de todo mundo, com a cadeira não dá para atravessar água. Ninguém sabe que ele mora aqui." | cadastro opcional de quem precisa de ajuda para sair (com consentimento LGPD); esses casos sobem na fila da Defesa Civil |
| Seu Raimundo, 58 anos, ilhado em 2009 e em setembro deste ano, Jardim Romano | conversa por WhatsApp (áudio), 12/11 | "Na enchente a luz cai e o celular fica sem sinal. O vizinho que avisa é quem salva." | estação com alarme local (LED e buzzer) que funciona sem internet; alerta curto que cabe num SMS |
| Patrícia, agente voluntária do Nudec, Jardim Helena | conversa por videochamada, 13/11 | "No dia da cheia chegam cem pedidos ao mesmo tempo no grupo. A gente atende quem grita mais alto, não quem está pior." | fila priorizada pela IA (gravidade, vulneráveis e risco do bairro) e check-in "Estou seguro / Preciso de ajuda" |
| Lucas, 22 anos, neto de idosa acamada, Jardim Pantanal | conversa presencial, 14/11 | "Eu trabalho no centro. Queria saber de longe se a minha avó respondeu ou não." | painel de check-ins mostra quem ainda não respondeu; alerta indica o ponto de apoio acessível mais perto |

## O que mudou por causa das entrevistas
- Acessibilidade virou padrão no app do morador: letra grande, alto contraste e leitura do alerta em voz.
- Alerta mais cedo e mais curto: a rede neural antecipa o aviso e o texto cabe num SMS de 160 caracteres.
- A estação IoT passou a ter alarme local, porque luz e sinal de celular caem justamente na enchente.
- Pessoas com mobilidade reduzida entram na fila com prioridade maior, sempre com consentimento.
- O check-in virou a principal informação para a Defesa Civil saber quem ainda precisa de visita.
