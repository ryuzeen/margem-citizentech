/*
 * Margem - estação IoT de nível do rio (ESP32 no Wokwi)
 * FIAP Global Solution 2026/2 - CitizenTech
 *
 * Sensores (simulados no Wokwi):
 *   - HC-SR04 apontado para a água: nível = ALTURA_INSTALACAO_CM - distância
 *   - potenciômetro  = pluviômetro (0-200 mm/h)
 *   - slide-pot      = umidade do solo (0-100 %)
 * Saídas locais (funcionam SEM internet): OLED com nível/risco, LEDs verde/amarelo/vermelho e buzzer.
 * Rede (quando houver): WiFi Wokwi-GUEST -> NTP (hora -03:00) -> MQTT no broker público.
 * Cada leitura vai em JSON com seq (anti-replay) e sig = HMAC-SHA256(token, mensagem canônica),
 * a mesma regra de comum/seguranca_iot.py:
 *   "{estacao_id}|{ts}|{seq}|{nivel_cm:.1f}|{chuva_mm_h:.1f}|{umidade_solo_pct:.1f}"
 * Sem broker, as leituras ficam numa fila (store-and-forward) e são enviadas quando a rede volta.
 */
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <time.h>
#include "mbedtls/md.h"

// ---------------- configuração da estação (valores de DEMONSTRAÇÃO, ver .env.example) ----------------
const char* ESTACAO_ID = "EST-PANTANAL-01";
const char* TOKEN_ESTACAO = "demo-pantanal-7c1f";   // MARGEM_TOKEN_EST_PANTANAL_01
const char* FIRMWARE = "1.0.0";
const float ALTURA_INSTALACAO_CM = 520.0;           // config/territorio.json
const float COTA_ALERTA_CM = 260.0;
const float COTA_TRANSBORDO_CM = 340.0;

const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_SENHA = "";
const char* MQTT_HOST = "broker.hivemq.com";        // MARGEM_MQTT_HOST
const int MQTT_PORTA = 1883;                        // MARGEM_MQTT_PORTA
const char* NTP_1 = "pool.ntp.org";
const char* NTP_2 = "time.google.com";

// true = não tenta rede: demonstra que o alarme local funciona sem conectividade.
const bool MODO_SEM_REDE = false;
const unsigned long INTERVALO_LEITURA_MS = 5000;    // demo: uma leitura a cada 5 s
const int TAMANHO_FILA = 30;                        // leituras guardadas enquanto o broker está fora

// ---------------- pinos ----------------
const int PINO_TRIG = 5;
const int PINO_ECHO = 18;
const int PINO_CHUVA = 34;      // potenciômetro
const int PINO_UMIDADE = 35;    // slide-potentiometer
const int PINO_LED_VERDE = 25;
const int PINO_LED_AMARELO = 26;
const int PINO_LED_VERMELHO = 27;
const int PINO_BUZZER = 13;

Adafruit_SSD1306 tela(128, 64, &Wire, -1);
WiFiClient wifiCliente;
PubSubClient mqtt(wifiCliente);

enum Risco { OBSERVACAO, ATENCAO, ALERTA, ALERTA_MAXIMO };
const char* ROTULO_RISCO[] = {"OBSERVACAO", "ATENCAO", "ALERTA", "ALERTA MAXIMO"};

String fila[TAMANHO_FILA];
int filaInicio = 0, filaTamanho = 0;

unsigned long seq = 0;            // definido a partir do relógio na 1ª sincronização NTP
bool relogioOk = false;
float nivelCm = 0, chuvaMmH = 0, umidadePct = 0;
bool sensorOk = true;
Risco risco = OBSERVACAO;
unsigned long ultimaLeitura = 0, ultimaTentativaMqtt = 0, ultimoBip = 0;
char topico[80];

// ---------------- segurança: HMAC-SHA256 em hexadecimal ----------------
String hmacSha256(const char* chave, const char* mensagem) {
  unsigned char saida[32];
  mbedtls_md_context_t ctx;
  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), 1);  // 1 = modo HMAC
  mbedtls_md_hmac_starts(&ctx, (const unsigned char*)chave, strlen(chave));
  mbedtls_md_hmac_update(&ctx, (const unsigned char*)mensagem, strlen(mensagem));
  mbedtls_md_hmac_finish(&ctx, saida);
  mbedtls_md_free(&ctx);
  char hex[65];
  for (int i = 0; i < 32; i++) sprintf(hex + 2 * i, "%02x", saida[i]);
  hex[64] = '\0';
  return String(hex);
}

// ---------------- sensores ----------------
float medirDistanciaCm() {
  digitalWrite(PINO_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PINO_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PINO_TRIG, LOW);
  unsigned long duracao = pulseIn(PINO_ECHO, HIGH, 30000);  // timeout ~5 m
  if (duracao == 0) return -1;                              // sem eco: sensor com problema
  return duracao * 0.0343 / 2.0;
}

void lerSensores() {
  float distancia = medirDistanciaCm();
  sensorOk = distancia > 0;
  if (sensorOk) nivelCm = constrain(ALTURA_INSTALACAO_CM - distancia, 0, 600);  // mantém o último se falhar
  chuvaMmH = analogRead(PINO_CHUVA) * 200.0 / 4095.0;
  umidadePct = analogRead(PINO_UMIDADE) * 100.0 / 4095.0;
}

Risco calcularRisco(float nivel) {  // regra por cota (docs/CONTRATOS.md §3)
  if (nivel >= COTA_TRANSBORDO_CM) return ALERTA_MAXIMO;
  if (nivel >= COTA_ALERTA_CM) return ALERTA;
  if (nivel >= 0.6 * COTA_ALERTA_CM) return ATENCAO;
  return OBSERVACAO;
}

// ---------------- alarme local (não depende de rede) ----------------
void atualizarAlarme() {
  unsigned long agora = millis();
  bool pisca = (agora / 400) % 2;
  digitalWrite(PINO_LED_VERDE, risco == OBSERVACAO);
  digitalWrite(PINO_LED_AMARELO, risco == ATENCAO);
  digitalWrite(PINO_LED_VERMELHO, risco == ALERTA || (risco == ALERTA_MAXIMO && pisca));
  if (risco == ALERTA_MAXIMO && agora - ultimoBip >= 800) {        // sirene intermitente
    tone(PINO_BUZZER, 2200, 400);
    ultimoBip = agora;
  } else if (risco == ALERTA && agora - ultimoBip >= 10000) {      // bip curto a cada 10 s
    tone(PINO_BUZZER, 1500, 150);
    ultimoBip = agora;
  }
}

void desenharTela() {
  tela.clearDisplay();
  tela.setTextColor(SSD1306_WHITE);
  tela.setTextSize(1);
  tela.setCursor(0, 0);
  tela.print("MARGEM ");
  tela.println(ESTACAO_ID + 4);  // sem o prefixo "EST-"
  tela.setTextSize(2);
  tela.setCursor(0, 12);
  if (sensorOk) {
    tela.print(nivelCm, 0);
    tela.print(" cm");
  } else {
    tela.print("SENSOR?");
  }
  tela.setTextSize(1);
  tela.setCursor(0, 32);
  tela.printf("Chuva %.0f mm/h Solo %.0f%%", chuvaMmH, umidadePct);
  tela.setCursor(0, 42);
  tela.printf("Cota %.0f%%  ", nivelCm / COTA_ALERTA_CM * 100);
  tela.print(ROTULO_RISCO[risco]);
  tela.setCursor(0, 54);
  if (MODO_SEM_REDE || WiFi.status() != WL_CONNECTED) tela.print("OFFLINE");
  else tela.print(mqtt.connected() ? "MQTT ok" : "WiFi ok");
  tela.printf("  fila:%d", filaTamanho);
  tela.display();
}

// ---------------- rede ----------------
void enfileirar(const String& payload) {
  if (filaTamanho == TAMANHO_FILA) {  // fila cheia: descarta a mais antiga
    filaInicio = (filaInicio + 1) % TAMANHO_FILA;
    filaTamanho--;
  }
  fila[(filaInicio + filaTamanho) % TAMANHO_FILA] = payload;
  filaTamanho++;
}

void esvaziarFila() {
  while (filaTamanho > 0 && mqtt.connected()) {
    if (!mqtt.publish(topico, fila[filaInicio].c_str())) break;
    Serial.print("enviado: ");
    Serial.println(fila[filaInicio]);
    filaInicio = (filaInicio + 1) % TAMANHO_FILA;
    filaTamanho--;
  }
}

void manterRede() {
  if (MODO_SEM_REDE || WiFi.status() != WL_CONNECTED) return;
  if (!relogioOk) {
    struct tm agora;
    if (getLocalTime(&agora, 0)) {
      relogioOk = true;
      seq = (unsigned long)time(nullptr);  // monotônico entre reinícios (nunca repete seq já usado)
      Serial.println("NTP sincronizado");
    }
  }
  if (!mqtt.connected() && millis() - ultimaTentativaMqtt > 5000) {
    ultimaTentativaMqtt = millis();
    String id = String("margem-") + ESTACAO_ID + "-" + String((uint32_t)ESP.getEfuseMac(), HEX);
    if (mqtt.connect(id.c_str())) Serial.println("MQTT conectado");
  }
  mqtt.loop();
  esvaziarFila();
}

String montarPayload() {
  struct tm agora;
  getLocalTime(&agora, 0);
  char ts[32], nivelTxt[12], chuvaTxt[12], umidadeTxt[12];
  strftime(ts, sizeof(ts), "%Y-%m-%dT%H:%M:%S-03:00", &agora);
  // As mesmas strings com 1 casa entram na assinatura e no JSON: servidor e ESP32 assinam o mesmo texto.
  snprintf(nivelTxt, sizeof(nivelTxt), "%.1f", nivelCm);
  snprintf(chuvaTxt, sizeof(chuvaTxt), "%.1f", chuvaMmH);
  snprintf(umidadeTxt, sizeof(umidadeTxt), "%.1f", umidadePct);
  seq++;
  char mensagem[160];
  snprintf(mensagem, sizeof(mensagem), "%s|%s|%lu|%s|%s|%s", ESTACAO_ID, ts, seq, nivelTxt, chuvaTxt, umidadeTxt);

  JsonDocument doc;
  doc["estacao_id"] = ESTACAO_ID;
  doc["ts"] = ts;
  doc["seq"] = seq;
  doc["nivel_cm"] = serialized(nivelTxt);
  doc["chuva_mm_h"] = serialized(chuvaTxt);
  doc["umidade_solo_pct"] = serialized(umidadeTxt);
  doc["bateria_pct"] = 100 - (int)min(60UL, millis() / 600000UL);  // demo: bateria cai devagar
  doc["firmware"] = FIRMWARE;
  doc["sig"] = hmacSha256(TOKEN_ESTACAO, mensagem);
  String saida;
  serializeJson(doc, saida);
  return saida;
}

// ---------------- setup / loop ----------------
void setup() {
  Serial.begin(115200);
  pinMode(PINO_TRIG, OUTPUT);
  pinMode(PINO_ECHO, INPUT);
  pinMode(PINO_LED_VERDE, OUTPUT);
  pinMode(PINO_LED_AMARELO, OUTPUT);
  pinMode(PINO_LED_VERMELHO, OUTPUT);
  pinMode(PINO_BUZZER, OUTPUT);
  if (!tela.begin(SSD1306_SWITCHCAPVCC, 0x3C)) Serial.println("OLED nao encontrado");
  snprintf(topico, sizeof(topico), "margem/v1/estacoes/%s/leituras", ESTACAO_ID);

  if (!MODO_SEM_REDE) {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_SENHA, 6);  // canal 6 acelera a conexão no Wokwi
    configTime(-3 * 3600, 0, NTP_1, NTP_2);
    mqtt.setServer(MQTT_HOST, MQTT_PORTA);
    mqtt.setBufferSize(512);
  }
  Serial.println("Margem: estacao iniciada (alarme local ativo mesmo sem rede)");
}

void loop() {
  manterRede();
  if (millis() - ultimaLeitura >= INTERVALO_LEITURA_MS || ultimaLeitura == 0) {
    ultimaLeitura = millis();
    lerSensores();
    risco = calcularRisco(nivelCm);
    if (relogioOk) {  // sem hora confiável não dá para assinar o ts: só alarme local
      String payload = montarPayload();
      if (mqtt.connected() && mqtt.publish(topico, payload.c_str())) {
        Serial.print("enviado: ");
        Serial.println(payload);
      } else {
        enfileirar(payload);
        Serial.printf("sem broker: leitura na fila (%d)\n", filaTamanho);
      }
    } else {
      Serial.printf("nivel=%.1f cm risco=%s (aguardando rede/NTP)\n", nivelCm, ROTULO_RISCO[risco]);
    }
    desenharTela();
  }
  atualizarAlarme();
  delay(20);
}
