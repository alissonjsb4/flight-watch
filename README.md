# flight-watch

Monitor de preço de passagens aéreas que roda sozinho, guarda a série histórica e
avisa no Telegram **só quando a informação muda** — não a cada checagem.

Rodou de forma autônoma por 6 semanas: **636 execuções, 497 leituras de preço
válidas e 5 alertas enviados.** A supressão de ruído é o ponto do projeto.

![Série histórica de preços coletada pelo flight-watch](docs/price-history.png)

---

## O problema

Monitorar preço de passagem à mão é inviável: o valor muda várias vezes ao dia e
você não vai abrir o site de hora em hora. Automatizar a checagem é a parte fácil.
A parte difícil é **não transformar isso em spam** — um alerta por execução seriam
497 mensagens em 6 semanas, e você para de ler na terceira.

## A solução

O sistema divide a faixa de preço em degraus (`tiers`) e mantém, em disco, qual
degrau estava valendo na última execução. Só notifica quando o preço **atravessa**
um degrau — para baixo ou para cima.

```
preço lido ──▶ em que degrau caiu? ──▶ mudou desde a última vez?
                                          │
                            não ──────────┤────────── sim
                              │                        │
                        só registra                notifica + registra
```

Resultado prático: **5 alertas em 497 leituras**. Cada mensagem que chegou no
Telegram significava uma mudança real de patamar.

O degrau é re-armado nos dois sentidos. Se o preço sobe e volta a cair, você é
avisado de novo — um sistema que só notifica na descida fica mudo para sempre
depois do primeiro alerta.

## Resultados

| Métrica | Valor |
|---|---|
| Execuções registradas | 636 (24/06 a 06/08/2026) |
| Execuções na janela útil | 506 |
| Leituras com preço | **497 — 98% da janela útil** |
| Falhas de coleta | 9 |
| Alertas enviados | **5** |
| Preço mínimo / máximo | R$ 1.561,13 / R$ 5.150,83 (**variação de 3,3x**) |

A "janela útil" vai até a data da viagem monitorada. Depois disso a busca deixa de
retornar resultado — as 130 execuções seguintes sem preço são comportamento
esperado, não falha (ver [Limitações](#limitações-conhecidas)).

## Decisões de projeto

**Ler o preço certo.** A página expõe dois valores: `span.value` é a tarifa-base
sem taxas, e `span.price-pointer` é o total já com taxas. Usar o primeiro
subestimaria o preço real em centenas de reais e dispararia alertas falsos. O
seletor foi escolhido depois de conferir os dois contra o checkout.

**Filtro de sanidade.** Valores abaixo de `noise_floor` são descartados — evita que
um elemento de layout ou uma promoção parcial entre como preço válido.

**Estado versionado em disco.** `state.json` guarda degrau atual, menor preço já
visto e contador de execuções. O código migra o formato antigo (`min_tier_notified`)
para o atual (`current_tier`) na leitura, sem perder histórico.

**Falha isolada por etapa.** Erro na coleta registra no log, persiste o estado e sai
com código 1 (o agendador enxerga a falha). Erro no envio do Telegram é registrado
mas não derruba a execução nem descarta a leitura já coletada.

**Preparado para rodar sem sessão de usuário.** O Chromium fica dentro do próprio
projeto via `PLAYWRIGHT_BROWSERS_PATH`, e o navegador sobe com `--no-sandbox` /
`--disable-dev-shm-usage`, necessários quando a tarefa roda como SYSTEM.

**Timestamps com fuso.** Tudo em ISO 8601 com `America/Fortaleza`, para a série
histórica continuar correta em horário de verão ou troca de máquina.

## Como rodar

```bash
pip install -r requirements.txt && playwright install chromium
cp config.example.json config.json   # preencha url, tiers e credenciais do Telegram
python watch.py
```

Para gerar o gráfico e o resumo da série coletada:

```bash
python analyze.py
```

### Agendamento

Cada execução é independente e idempotente — todo o estado vive em `state.json`.
Basta chamar `watch.py` de hora em hora com qualquer agendador:

- **Windows** — Agendador de Tarefas. Rodando como SYSTEM, defina
  `FLIGHT_WATCH_SITE_PACKAGES` apontando para o `site-packages` do usuário.
- **Linux** — `cron` ou um timer do `systemd`.

## Limitações conhecidas

- **Não tem condição de parada.** O monitor continua rodando depois da data da
  viagem, quando a busca já não retorna nada. É a origem das 130 execuções vazias
  no fim da série. O conserto natural é encerrar a tarefa na data de ida.
- **Acoplado ao HTML de um site.** Mudança de layout quebra o seletor. Hoje isso
  aparece como leitura vazia no log, sem falso positivo — mas exige revisão manual.
- **Uma rota por instância.** Monitorar várias rotas hoje significa várias cópias
  com `config.json` diferentes.

## Estrutura

```
watch.py              coleta, decide e notifica (uma execução)
analyze.py            resumo estatístico + gráfico da série
config.example.json   modelo de configuração
history.csv           série histórica (timestamp, menor preço)
docs/                 gráfico gerado
```

`config.json`, `state.json` e `watch.log` ficam fora do versionamento — o primeiro
por conter credenciais, os outros dois por serem estado de execução.

## Stack

Python 3.14 · Playwright · requests · pandas · matplotlib · API do Telegram

---

Feito por [Alisson Jaime](https://github.com/alissonjsb4) — nasceu de um assistente
pessoal em Telegram que eu mantinha, e virou projeto próprio quando a parte de
coleta e notificação se mostrou mais útil sozinha.
