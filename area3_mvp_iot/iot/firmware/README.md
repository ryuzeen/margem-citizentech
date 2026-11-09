# Firmware da estação Margem (ESP32 no Wokwi)

Estação **EST-PANTANAL-01** (margem do Tietê, Jardim Pantanal). Mede o nível do rio, a chuva e a umidade
do solo, mostra o risco no display e **toca o alarme local mesmo sem internet**. Quando há rede, envia as
leituras por MQTT, assinadas com HMAC-SHA256 (mesma regra de `comum/seguranca_iot.py`, contrato §4).

| Componente (Wokwi) | Papel | Pino ESP32 |
|---|---|---|
| HC-SR04 | distância até a água → `nivel = 520 − distância` (cm) | TRIG 5, ECHO 18 |
| Potenciômetro | pluviômetro (0–200 mm/h) | 34 |
| Slide potentiometer | umidade do solo (0–100 %) | 35 |
| OLED SSD1306 (I2C 0x3C) | nível, chuva, solo, % da cota, risco, estado da rede, fila | SDA 21, SCL 22 |
| LEDs verde / amarelo / vermelho | observação / atenção / alerta (pisca = alerta máximo) | 25 / 26 / 27 |
| Buzzer | bip a cada 10 s em alerta; sirene em alerta máximo | 13 |

Cotas (de `config/territorio.json`): alerta **260 cm**, transbordo **340 cm**, atenção a partir de 156 cm
(60 % da cota de alerta). Token de demonstração: o mesmo de `.env.example` (`MARGEM_TOKEN_EST_PANTANAL_01`).

## Rodar no wokwi.com (navegador, sem instalar nada)
1. Acesse https://wokwi.com → **New Project** → **ESP32** (template "ESP32", Arduino).
2. Na aba `sketch.ino`, apague o conteúdo e cole o `sketch.ino` desta pasta.
3. Na aba `diagram.json`, cole o `diagram.json` desta pasta (os componentes aparecem ligados).
4. Bibliotecas: clique no **+** ao lado das abas → **New file…** → `libraries.txt` e cole o `libraries.txt`
   desta pasta (ou use o Library Manager e adicione PubSubClient, ArduinoJson, Adafruit SSD1306 e
   Adafruit GFX Library).
5. Clique em **▶ Start Simulation**. O monitor serial mostra a conexão WiFi (`Wokwi-GUEST`), NTP e MQTT.

## O que observar
- **Nível**: clique no HC-SR04 e mova o controle de distância. Distância 320 cm → nível 200 cm (atenção,
  LED amarelo). Distância ≤ 260 cm → nível ≥ 260 (alerta, LED vermelho + bip). Distância ≤ 180 cm →
  nível ≥ 340 (alerta máximo: vermelho piscando + sirene).
- **Chuva / solo**: gire o potenciômetro e arraste o slide; os valores aparecem no OLED e no JSON.
- **Serial**: cada leitura sai como `enviado: {"estacao_id":"EST-PANTANAL-01","ts":"…-03:00","seq":…,
  "nivel_cm":200.0,…,"sig":"…"}` no tópico `margem/v1/estacoes/EST-PANTANAL-01/leituras`.
- **Sem conectividade**: troque `MODO_SEM_REDE` para `true` no topo do sketch e rode de novo. O OLED mostra
  `OFFLINE` e LEDs/buzzer continuam reagindo ao nível — o alerta local não depende da rede. Com rede mas
  sem broker, as leituras entram numa fila (`fila:N` no OLED, até 30) e são enviadas quando o MQTT volta.

## Receber as leituras no Margem
No computador (raiz do projeto), com `MARGEM_MQTT_HOST=broker.hivemq.com` no `.env`:

```
.venv/Scripts/python -m area2_bigdata.ingestao.ponte_mqtt --api http://127.0.0.1:8080
```
A ponte valida assinatura, faixa, `seq` (anti-replay) e horário; leituras inválidas vão para
`dados/data_lake/quarentena/leituras.csv`. Sem `--api`, grava direto na camada bruta do data lake.

## Segurança (demonstração)
- O token fica no firmware só para a demo acadêmica; em produção iria para a NVS/flash criptografada e
  seria diferente por estação. O broker público não tem TLS nem senha: a integridade vem do HMAC + `seq`.
- `seq` começa no horário Unix da 1ª sincronização NTP e só cresce, então um reinício não repete `seq`.

## VS Code (opcional)
Com a extensão Wokwi e o `arduino-cli`: copie esta pasta para uma pasta chamada `sketch` (o arduino-cli
exige o nome da pasta igual ao do `.ino`), rode
`arduino-cli compile --fqbn esp32:esp32:esp32 --output-dir build .` e abra o `diagram.json`
(o `wokwi.toml` aponta para `build/sketch.ino.bin`).
