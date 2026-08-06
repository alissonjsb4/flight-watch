# flight-watch

Monitor de preço de passagens aéreas. Coleta o menor preço de uma rota de hora em
hora, grava a série em CSV e notifica no Telegram quando o preço cruza uma faixa
configurada.

## Uso

    pip install -r requirements.txt && playwright install chromium
    cp config.example.json config.json
    python watch.py      # uma coleta
    python analyze.py    # resumo e gráfico da série

Cada execução é independente e o estado fica em `state.json`. Agende com cron,
timer do systemd ou Agendador de Tarefas do Windows.

## Funcionamento

Playwright carrega a página de resultados e extrai `span.price-pointer`, o preço
total com taxas. Valores abaixo de `noise_floor` são descartados.

O menor preço é mapeado para uma faixa de `tiers`. A notificação dispara quando a
faixa difere da registrada na execução anterior, nos dois sentidos: a faixa é
rearmada na alta, então uma queda posterior volta a notificar.

## Resultados

636 execuções entre 24/06 e 06/08/2026. Na janela em que a busca ainda retornava
resultado, 497 de 506 execuções coletaram preço. Cinco notificações enviadas.

![Série de preços coletada](docs/price-history.png)

## Notas

- O seletor é `span.price-pointer` porque `span.value` expõe a tarifa-base sem
  taxas e subestimaria o preço em centenas de reais.
- Sem condição de parada: o monitor segue rodando depois da data da viagem, o que
  gera as leituras vazias no fim da série.
- Uma rota por instância; várias rotas são várias cópias com `config.json` próprios.
- Para rodar como SYSTEM no Windows, `FLIGHT_WATCH_SITE_PACKAGES` aponta o
  site-packages do usuário e o Chromium fica em `browsers/` dentro do projeto.

## Stack

Python 3.14, Playwright, requests, pandas, matplotlib.
