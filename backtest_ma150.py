"""Rueckblick: "Verkaufen, wenn der Kurs einen abflachenden 150-Tage-Durchschnitt nach unten durchbricht".

Regel (nur Daten bis zum Signaltag, Ausfuehrung zum naechsten Eroeffnungskurs):
  Verkauf:  Schlusskurs liegt (BESTAETIGUNG Tage in Folge) unter dem 150-Tage-Schnitt UND der Schnitt ist flach oder faellt,
            d. h. seine Veraenderung ueber STEIGUNGSTAGE Tage ist <= SCHWELLE.
  Kauf:     Schlusskurs wieder ueber dem Schnitt ("ueber") bzw. zusaetzlich Schnitt steigt ("ueber+steigt").
Zum Vergleich: "Einfach" = ohne Steigungsfilter (verkaufen sobald unter dem Schnitt) und Buy & Hold.
Kosten: 0,1 % pro Kauf und pro Verkauf. Keine Anlageberatung.
Umgebung: TICKERS (Komma-getrennt, Standard AAPL,SPY,INTC), YEARS (Standard 12; die ersten 150 Tage dienen nur dem Einschwingen).
"""
import itertools
import json
import os
import sys

import numpy as np
import pandas as pd

MA = 150
COST = 0.001
STEIGUNGSTAGE = (10, 20)
SCHWELLEN = (0.0, 0.01, 0.02)      # Aenderung des Schnitts ueber STEIGUNGSTAGE, <= Schwelle gilt als flach/fallend
BESTAETIGUNG = (1, 3)
WIEDEREINSTIEG = ("ueber", "ueber+steigt")


def simulate(o, c, ma, slope, thr, confirm, reentry, use_slope=True):
    """Taegliche Equity-Kurve ab Startindex. Signal am Schlusskurs von Tag t, Ausfuehrung zum Eroeffnungskurs von t+1."""
    n = len(c)
    start = MA + max(STEIGUNGSTAGE) + 1
    eq, pos, below, pending = 1.0 - COST, 1, 0, None
    entry_px, trades, days_in = c[start - 1], [], 0
    equity = np.full(n, np.nan)
    for t in range(start, n):
        if pending == "sell" and pos == 1:
            eq *= o[t] / c[t - 1] * (1 - COST)
            trades.append(o[t] / entry_px - 1)
            pos = 0
        elif pending == "buy" and pos == 0:
            eq *= (1 - COST) * c[t] / o[t]
            entry_px, pos = o[t], 1
        elif pos == 1:
            eq *= c[t] / c[t - 1]
        pending = None
        equity[t] = eq
        days_in += pos
        under = c[t] < ma[t]
        below = below + 1 if under else 0
        flat = (not use_slope) or slope[t] <= thr
        if pos == 1 and below >= confirm and flat:
            pending = "sell"
        elif pos == 0 and not under and (reentry == "ueber" or slope[t] > 0):
            pending = "buy"
    if pos == 1:
        trades.append(c[-1] / entry_px - 1)
    return equity, trades, days_in / (n - start)


def metrics(equity, start, trades, exposure):
    e = equity[start:]
    years = len(e) / 252.0
    dd = float((e / np.maximum.accumulate(e) - 1).min())
    tot = e[-1] / e[0] - 1
    r = np.array(trades) if trades else np.array([0.0])
    return {"gesamt_pct": round(100 * tot, 1), "jahr_pct": round(100 * ((1 + tot) ** (1 / years) - 1), 1),
            "max_verlust_pct": round(100 * dd, 1), "trades": len(trades),
            "trefferquote_pct": round(100 * float((r > 0).mean()), 1), "im_markt_pct": round(100 * exposure, 1)}


def run_ticker(df):
    o, c = df["Open"].to_numpy(float), df["Close"].to_numpy(float)
    ma = pd.Series(c).rolling(MA).mean().to_numpy()
    start = MA + max(STEIGUNGSTAGE) + 1
    bh = c[start:] / c[start]
    years = len(bh) / 252.0
    bh_res = {"gesamt_pct": round(100 * (bh[-1] - 1), 1), "jahr_pct": round(100 * (bh[-1] ** (1 / years) - 1), 1),
              "max_verlust_pct": round(100 * float((bh / np.maximum.accumulate(bh) - 1).min()), 1)}
    out = []
    for sd, thr, cf, re_ in itertools.product(STEIGUNGSTAGE, SCHWELLEN, BESTAETIGUNG, WIEDEREINSTIEG):
        slope = np.full(len(c), np.nan)
        slope[sd:] = ma[sd:] / ma[:-sd] - 1
        eq, tr, ex = simulate(o, c, ma, slope, thr, cf, re_)
        m = metrics(eq, start, tr, ex)
        m.update({"steigungstage": sd, "schwelle_pct": thr * 100, "bestaetigung": cf, "wiedereinstieg": re_, "variante": "flach"})
        out.append(m)
    for cf, re_ in itertools.product(BESTAETIGUNG, WIEDEREINSTIEG):
        slope = np.full(len(c), np.nan)
        slope[20:] = ma[20:] / ma[:-20] - 1
        eq, tr, ex = simulate(o, c, ma, slope, 0, cf, re_, use_slope=False)
        m = metrics(eq, start, tr, ex)
        m.update({"steigungstage": None, "schwelle_pct": None, "bestaetigung": cf, "wiedereinstieg": re_, "variante": "einfach"})
        out.append(m)
    return bh_res, out, df.index[start].date(), df.index[-1].date()


def main():
    import yfinance as yf
    tickers = [t.strip().upper() for t in os.environ.get("TICKERS", "AAPL,SPY,INTC").split(",") if t.strip()]
    years = int(os.environ.get("YEARS", "12"))
    allres = {}
    for tk in tickers:
        raw = None
        for _ in range(3):
            raw = yf.download(tk, period="%dy" % years, interval="1d", auto_adjust=True, progress=False, threads=False)
            if raw is not None and not raw.empty:
                break
        if raw is None or raw.empty:
            print("Keine Daten fuer", tk)
            continue
        cols = {}
        for k in ("Open", "Close"):
            x = raw[k]
            cols[k] = x.iloc[:, 0] if hasattr(x, "columns") else x
        df = pd.DataFrame(cols).dropna()
        bh, res, d0, d1 = run_ticker(df)
        allres[tk] = {"von": str(d0), "bis": str(d1), "buy_hold": bh, "ergebnisse": res}
        print("\n=== %s (%s bis %s) Buy & Hold: gesamt %+.1f %%, %.1f %% p. a., groesster Rueckgang %.1f %% ===" % (
            tk, d0, d1, bh["gesamt_pct"], bh["jahr_pct"], bh["max_verlust_pct"]))
        print("Variante Tage Schw% Best Wiedereinstieg | Trades Treffer% ImMarkt% Gesamt% Jahr% MaxVerl%")
        for r in sorted(res, key=lambda r: -r["jahr_pct"]):
            print("%-7s %4s %5s %4d %-12s | %6d %7.1f %8.1f %7.1f %5.1f %7.1f" % (
                r["variante"], r["steigungstage"], r["schwelle_pct"], r["bestaetigung"], r["wiedereinstieg"],
                r["trades"], r["trefferquote_pct"], r["im_markt_pct"], r["gesamt_pct"], r["jahr_pct"], r["max_verlust_pct"]))
    with open("backtest_ma150.json", "w", encoding="utf-8") as f:
        json.dump(allres, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
