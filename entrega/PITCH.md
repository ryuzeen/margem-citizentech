# Roteiro do vídeo pitch — Margem (até 3:00)

> **Para quem vai gravar.** Leia tudo uma vez antes. O vídeo vale **5 pontos**: problema e cidadão (1),
> demonstração das áreas (2), impacto e diferencial (1), clareza e tempo (1).
> **Regras do PDF:** até 3 minutos (o que passar disso não é avaliado), precisa **mostrar o site funcionando**
> (vídeo só de slides ou de leitura de texto não vale) e o link tem que ser público.

## Antes de gravar (10 min)

1. **Onde rodar a demo**
   - **Opção A, com a API real (recomendada):** na pasta do projeto, rode `python iniciar.py`. O navegador abre sozinho em `http://127.0.0.1:8080`.
   - **Opção B, sem instalar nada:** abra o link do GitHub Pages (está no README). Ele roda em *modo demonstração*, com o mesmo visual e o mesmo fluxo.
2. **Deixe 2 abas abertas lado a lado** (ou duas janelas):
   - **Aba 1, Console da Defesa Civil:** `/console.html`, login `operador@demo.margem.app` / `DefesaCivil@2026`.
   - **Aba 2, App do morador:** `/app.html`, login `maria@demo.margem.app` / `Margem@2026`. Para parecer celular, use o modo responsivo do navegador (F12 → ícone de celular, 390 px).
3. **Comece com o cenário "Normal"** no console (Estações IoT → Cenário → Normal), com todos os bairros em Observação.
4. **Gravação:** use OBS, ou a Barra de Jogo do Windows (Win+Alt+R). Grave em 1080p, feche as notificações e use fonte do navegador em 100%.
5. **Voz:** fale com calma. O texto abaixo dá cerca de 2:50 em ritmo normal. Treine 2 vezes com cronômetro.
6. **Opcional:** abra o ESP32 no Wokwi (link no README) numa terceira aba, para mostrar o sensor por 3 segundos.

## Roteiro

### 0:00 – 0:30 · O problema (tela: landing `index.html`)
**Na tela:** a landing parada no topo, com a régua do rio ao lado. Role devagar até "Do sensor ao socorro".

> "Em setembro deste ano, o Tietê transbordou de novo na zona leste de São Paulo. Jardim Pantanal,
> Jardim Helena, Vila Itaim: mais de três mil e quatrocentas pessoas foram cadastradas para receber ajuda, e teve
> família ilhada por três dias dizendo que *o apoio aqui é nós entre nós mesmos*.
> O problema não é só a chuva: é que o aviso chega tarde, numa linguagem difícil, e ninguém sabe
> quem precisa de socorro primeiro: o idoso que mora sozinho, a mãe com um filho cadeirante."

*(Fonte do dado, para o PDF/README: Brasil de Fato, 14/09/2026.)*

### 0:30 – 0:50 · A solução (tela: landing → "Do sensor ao socorro em quatro passos")
> "O Margem é uma CitizenTech de alerta comunitário de enchentes. Estações com sensores medem o rio,
> a chuva e o solo; uma inteligência artificial prevê o risco das próximas duas horas; o morador recebe o alerta em
> linguagem simples, por app, SMS ou voz; e a Defesa Civil recebe a fila de quem precisa de ajuda,
> já priorizada."

### 0:50 – 2:10 · Demonstração (o coração do vídeo: 80 segundos)

**① IoT + Big Data (0:50–1:10)**
**Na tela:** Console → **Estações IoT**. Mostre as 4 estações (nível, bateria, última leitura). Clique em **Cenário: Enchente**.
> "Aqui estão as quatro estações IoT, com ESP32, sensor ultrassônico, pluviômetro e umidade do solo. Cada
> leitura vem assinada, para ninguém forjar dado. Vou simular uma chuva forte..."

*(Enquanto fala, o nível sobe ao vivo.)* Se der tempo, mostre 2 s do Wokwi com o display OLED.

**② IA prevendo e alertando (1:10–1:30)**
**Na tela:** espere o Pantanal passar para **Alerta / Alerta máximo** (uns 20 s). Troque para a **aba do morador**: o alerta chegou sozinho.
> "...e antes de o rio transbordar, a rede neural já previu o risco e o agente comunicador escreveu este alerta:
> curto, cabe num SMS, diz o que fazer e onde fica o ponto de apoio acessível. Ela pode ouvir em voz alta."

Clique em **Ouvir alerta** por 2 s e depois em **Preciso de ajuda**.

**③ Multiagentes na triagem (1:30–1:50)**
**Na tela:** app do morador → **Relatar**. Digite (ou cole): *"a água tá entrando em casa e minha mãe é cadeirante"* → Enviar. Mostre o **rastro dos agentes** aparecendo.
> "Ela também pode escrever do jeito dela. Um sistema de agentes classifica o relato, busca o protocolo certo
> da Defesa Civil e calcula a prioridade: identificou água na casa, gravidade 4 e uma pessoa com deficiência."

**④ Console + Dashboard (1:50–2:10)**
**Na tela:** volte ao **Console → Fila**. O relato da Maria está no topo, e o pedido de ajuda aparece em **Check-ins**. Abra o **Dashboard** e troque o filtro de bairro uma vez.
> "Na Defesa Civil, o caso dela já está no topo da fila. E o dashboard junta um ano de dados do data lake:
> nível contra a cota, risco por bairro, tempo de atendimento e quantos vulneráveis estão em área de risco."

### 2:10 – 2:40 · Impacto e ODS (tela: Dashboard → indicador 6 "Antecedência do alerta")
> "O resultado que a gente mediu: com o modelo, o aviso chega em média **uma hora antes** do que pela régua
> do rio sozinha, e **82%** das enchentes são avisadas com duas horas ou mais de folga, contra 24%.
> Na triagem, a IA acerta a categoria em 87% dos relatos e encontra os vulneráveis em 97%.
> O Margem atende os ODS 11, cidades resilientes; 13, ação climática; 10, redução das desigualdades; e 3, saúde."

*(Antes de gravar, confira os números no dashboard e no `area1_ia/avaliacao/saida/relatorio_ia.md` e fale os que
estiverem lá. Se mudarem, atualize esta fala.)*

### 2:40 – 3:00 · Fechamento (tela: app do morador com "Estou seguro" ou landing)
> "Tecnologia que chega antes da água, e chega primeiro em quem mais precisa. Isso é o Margem.
> Obrigado!"

Mostre por 2 s o nome do grupo na tela (README ou landing) e encerre antes de **2:58**.

## Depois de gravar
1. Confira a duração: **≤ 3:00**.
2. Suba no YouTube como **Não listado** (ou no Google Drive com "qualquer pessoa com o link").
3. **Teste o link numa aba anônima.** Se o link estiver privado ou quebrado, o pitch não é avaliado.
4. Mande o link para o Rafa, que coloca no `.txt` da entrega e no README.

## Se algo der errado na gravação
- **O nível não sobe:** confira se o cenário está em "Enchente". Na opção A, veja se o terminal do `iniciar.py` continua aberto.
- **O alerta não chegou no app:** recarregue a aba do morador (F5). Ele aparece em "Meu alerta".
- **Quer recomeçar do zero:** Console → Estações IoT → Cenário "Recuperação" e depois "Normal". Na opção A, também dá para fechar e rodar `python iniciar.py --resetar`.
