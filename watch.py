"""
flight-watch — checa o preco da Zupper e avisa no Telegram quando cruza uma faixa.

Roda 1x por execucao (chamado de hora em hora pelo Agendador de Tarefas).
Cada faixa de preco avisa UMA vez (nao repete de hora em hora).
"""
import os
import json
import re
import sys
import csv
import html
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

# Usa uma pasta de browsers dentro do projeto, pra que tanto o usuario quanto a
# conta SYSTEM (tarefa rodando deslogado) encontrem o mesmo Chromium.
os.environ.setdefault(
    "PLAYWRIGHT_BROWSERS_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "browsers"),
)

# A tarefa agendada roda como SYSTEM (perfil diferente) e nao carrega o
# site-packages do usuario por padrao. FLIGHT_WATCH_SITE_PACKAGES aponta esse
# caminho sem precisar fixar o perfil de ninguem no codigo.
_user_site = os.environ.get("FLIGHT_WATCH_SITE_PACKAGES")
if _user_site and os.path.isdir(_user_site) and _user_site not in sys.path:
    sys.path.insert(0, _user_site)

import requests
from playwright.sync_api import sync_playwright

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
STATE_FILE = ROOT / "state.json"
LOG_CSV = ROOT / "history.csv"
TZ = ZoneInfo("America/Fortaleza")


def log(msg):
    ts = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with (ROOT / "watch.log").open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def read_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    # min_tier_notified = menor faixa ja avisada (infinito = nenhuma)
    return {"min_tier_notified": None, "lowest_seen": None, "checks": 0}


def write_state(s):
    STATE_FILE.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")


def append_history(price):
    new = not LOG_CSV.exists()
    with LOG_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "lowest_price"])
        w.writerow([datetime.now(TZ).isoformat(), price if price is not None else ""])


def parse_price(s):
    # "R$ 1.904,46" -> 1904.46
    digits = re.sub(r"[^\d,]", "", s).replace(".", "").replace(",", ".")
    try:
        return float(digits)
    except ValueError:
        return None


def fetch_lowest_price():
    """Carrega a pagina e retorna o menor preco total (float) ou None se falhar."""
    with sync_playwright() as p:
        # --no-sandbox etc.: necessario para rodar como SYSTEM (sessao 0) via agendador
        browser = p.chromium.launch(headless=True, args=[
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
        ])
        page = browser.new_page()
        try:
            page.goto(CONFIG["url"], wait_until="domcontentloaded", timeout=60000)
            try:
                # span.price-pointer = preco TOTAL em destaque de cada voo
                # (ja com taxas). NAO usar span.value, que mostra a tarifa-base
                # sem taxas e subestima o preco real.
                page.wait_for_selector("span.price-pointer", timeout=45000)
            except Exception:
                log("Nenhum 'span.price-pointer' apareceu (sem resultados ou layout mudou?).")
                return None
            page.wait_for_timeout(5000)
            texts = [e.inner_text() for e in page.query_selector_all("span.price-pointer")]
        finally:
            browser.close()

    prices = [v for v in (parse_price(t) for t in texts) if v is not None]
    prices = [v for v in prices if v >= CONFIG["noise_floor"]]  # sanidade
    if not prices:
        log("Nenhum preco total encontrado.")
        return None
    return min(prices)


def best_tier_crossed(price):
    """Menor faixa (valor) que o preco esta ABAIXO. None se acima de todas."""
    crossed = [t for t in CONFIG["tiers"] if price < t]
    return min(crossed) if crossed else None


def send_telegram(text):
    url = f"https://api.telegram.org/bot{CONFIG['telegram_token']}/sendMessage"
    r = requests.post(url, json={
        "chat_id": CONFIG["telegram_chat_id"],
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }, timeout=30)
    r.raise_for_status()
    log(f"Telegram enviado: {text[:60]}...")


def fmt(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    state = read_state()
    state["checks"] = state.get("checks", 0) + 1

    try:
        price = fetch_lowest_price()
    except Exception as e:
        log(f"ERRO ao buscar preco: {type(e).__name__}: {e}")
        write_state(state)
        sys.exit(1)

    append_history(price)

    if price is None:
        log("Sem preco nesta checagem.")
        write_state(state)
        return

    prev_low = state.get("lowest_seen")
    if prev_low is None or price < prev_low:
        state["lowest_seen"] = price
    log(f"Menor preco agora: {fmt(price)} (menor ja visto: {fmt(state['lowest_seen'])})")

    tier = best_tier_crossed(price)          # faixa atual (None = acima de todas)
    prev_tier = state.get("current_tier", "__unset__")
    if prev_tier == "__unset__":             # migra estado antigo
        prev_tier = state.get("min_tier_notified")

    # Avisa em QUALQUER mudanca de faixa: caiu (faixa mais baixa) ou subiu.
    # None = acima de todas as faixas (>= maior tier) -> tratado como infinito.
    tier_val = tier if tier is not None else float("inf")
    prev_val = prev_tier if prev_tier is not None else float("inf")
    banda = f"abaixo de <b>{fmt(tier)}</b>" if tier is not None else f"<b>acima de {fmt(CONFIG['tiers'][0])}</b>"

    direcao = None
    if tier_val < prev_val:
        direcao = ("📉 <b>Passagem caiu!</b>", "caiu")
    elif tier_val > prev_val:
        direcao = ("📈 <b>Passagem subiu</b>", "subiu")

    if direcao is not None:
        titulo, _ = direcao
        msg = (
            f"{titulo}\n"
            f"{html.escape(CONFIG['label'])}\n\n"
            f"Menor preco agora: <b>{fmt(price)}</b>\n"
            f"Faixa: {banda}\n\n"
            f"<a href=\"{html.escape(CONFIG['url'], quote=True)}\">Abrir na Zupper</a>"
        )
        try:
            send_telegram(msg)
        except Exception as e:
            log(f"ERRO ao enviar Telegram: {type(e).__name__}: {e}")
    else:
        log(f"Sem aviso (faixa atual={tier}, faixa anterior={prev_tier}).")

    # current_tier sempre segue a faixa atual (sobe e desce) -> re-arma na alta
    state["current_tier"] = tier
    state.pop("min_tier_notified", None)
    write_state(state)


if __name__ == "__main__":
    main()
