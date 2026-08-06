"""
analyze.py — resume a serie historica coletada pelo watch.py.

Le history.csv, imprime as estatisticas da coleta e gera docs/price-history.png.

Uso:
    python analyze.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # backend sem display: roda em servidor/CI
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent
HISTORY = ROOT / "history.csv"
OUT = ROOT / "docs" / "price-history.png"


def load():
    df = pd.read_csv(HISTORY, parse_dates=["timestamp"])
    df["ok"] = df["lowest_price"].notna()
    return df


def summarize(df):
    total = len(df)
    ok = int(df["ok"].sum())
    precos = df.loc[df["ok"], "lowest_price"]

    # A busca so retorna resultado ate a data da viagem monitorada. Depois disso
    # o monitor segue rodando e nao acha nada — separar as duas coisas evita
    # confundir "falha de coleta" com "fim do caso de uso".
    fim_janela = df.loc[df["ok"], "timestamp"].max()
    janela = df[df["timestamp"] <= fim_janela]
    ok_janela = int(janela["ok"].sum())

    print(f"Execucoes registradas    : {total}")
    print(f"Periodo                  : {df['timestamp'].min():%d/%m/%Y} a {df['timestamp'].max():%d/%m/%Y}")
    print()
    print(f"Janela util (ate {fim_janela:%d/%m/%Y})")
    print(f"  execucoes              : {len(janela)}")
    print(f"  leituras com preco     : {ok_janela} ({ok_janela / len(janela):.0%})")
    print(f"  falhas de coleta       : {len(janela) - ok_janela}")
    print()
    print(f"Apos a data da viagem     : {total - len(janela)} execucoes sem resultado (esperado)")
    print()
    print(f"Preco minimo             : R$ {precos.min():,.2f}")
    print(f"Preco maximo             : R$ {precos.max():,.2f}")
    print(f"Preco medio              : R$ {precos.mean():,.2f}")
    print(f"Variacao                 : {precos.max() / precos.min():.1f}x")
    print(f"Total de leituras validas: {ok}")


def plot(df):
    ok = df[df["ok"]]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.plot(ok["timestamp"], ok["lowest_price"], linewidth=1.1, color="#2b6cb0")
    ax.scatter(
        ok.loc[ok["lowest_price"].idxmin(), "timestamp"],
        ok["lowest_price"].min(),
        color="#c53030",
        zorder=3,
        s=28,
        label=f"minimo: R$ {ok['lowest_price'].min():,.2f}",
    )
    ax.set_title("flight-watch — menor preco observado por execucao (FOR <-> POA)")
    ax.set_ylabel("R$")
    ax.grid(alpha=0.25)
    ax.legend(loc="upper left", frameon=False)
    fig.autofmt_xdate()
    fig.tight_layout()
    OUT.parent.mkdir(exist_ok=True)
    fig.savefig(OUT, dpi=130)
    print(f"\nGrafico salvo em {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    frame = load()
    summarize(frame)
    plot(frame)
