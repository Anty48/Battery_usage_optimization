"""
src/data.py — Official hourly data pipeline of the challenge and the local validation split.

Usage:
    from src.data import load_hourly, is_pseudotest, split, blocks
    df = load_hourly()                 # columns: load_kw, pv_kw, precio_eur_per_kwh, co2_kg_per_kwh
    train, val = split(df)             # val = days 15–21 of every month (pseudo-test), train = the rest
    for b in blocks(val): ...          # list of contiguous 7-day DataFrames

Reproduces exactly the organisers' code (tutorial.ipynb): clip 0–5000, sum of the 3 inverters,
1 h mean resampling. The result is cached in results/cache/hourly_official.pkl.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "train"
CACHE = ROOT / "results" / "cache" / "hourly_official.pkl"

COLUMNS = ["load_kw", "pv_kw", "precio_eur_per_kwh", "co2_kg_per_kwh"]


def load_hourly(force: bool = False) -> pd.DataFrame:
    """Consolidated hourly table built with the official procedure. Index: Fecha (local time)."""
    if CACHE.exists() and not force:
        return pd.read_pickle(CACHE)[COLUMNS]

    c = pd.read_csv(DATA / "contador.csv", parse_dates=["Fecha"], low_memory=False).set_index("Fecha")
    load = (-c["Contador - POTENCIA ACTIVA EXPORTADA (kW)"]).clip(lower=0, upper=5000)
    load_h = load.resample("1h").mean().dropna()

    inv = pd.read_csv(DATA / "inversor.csv", parse_dates=["Fecha"], low_memory=False).set_index("Fecha")
    cols = [k for k in inv.columns if "POTENCIA ACTIVA" in k and "FASE" not in k]
    pv = inv[cols].sum(axis=1).clip(lower=0)
    pv_h = pv.resample("1h").mean().dropna()

    p = pd.read_csv(DATA / "precio_pvpc.csv", parse_dates=["Fecha"]).set_index("Fecha")
    co = pd.read_csv(DATA / "co2_red.csv", parse_dates=["Fecha"]).set_index("Fecha")

    df = pd.DataFrame({
        "load_kw": load_h,
        "pv_kw": pv_h,
        "precio_eur_per_kwh": p["precio_eur_per_kwh"],
        "co2_kg_per_kwh": co["co2_kg_per_kwh"],
    }).dropna()
    df.index.name = "Fecha"
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    df.to_pickle(CACHE)
    return df


def is_pseudotest(index: pd.DatetimeIndex) -> pd.Series:
    """True on days 15–21 of each month (our imitation of the hidden 'test weeks')."""
    return pd.Series((index.day >= 15) & (index.day <= 21), index=index)


def split(df: pd.DataFrame):
    """(train, val). Every parameter must be fitted on train ONLY."""
    m = is_pseudotest(df.index)
    return df[~m.values].copy(), df[m.values].copy()


def blocks(df: pd.DataFrame, max_gap_hours: float = 2.0):
    """Splits an hourly DataFrame into contiguous blocks (cuts where the gap > max_gap_hours)."""
    if len(df) == 0:
        return []
    gaps = df.index.to_series().diff().dt.total_seconds().div(3600).fillna(1.0)
    ids = (gaps > max_gap_hours).cumsum()
    return [g for _, g in df.groupby(ids.values)]


if __name__ == "__main__":
    df = load_hourly()
    tr, va = split(df)
    print(f"total {len(df)} h | train {len(tr)} h | pseudo-test {len(va)} h in {len(blocks(va))} blocks")
    print(df.describe().round(3))
