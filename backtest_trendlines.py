"""Rueckblick: Trendlinien-Abpraller (Support-Linie in einem Aufwaertstrend) an einem Wert.

Die Linien werden fuer jeden Tag NUR mit den Daten bis zum Vortag berechnet (kein Blick in die Zukunft).

Linie: Anker = tiefster Tief-Kurs im Fenster (Lookback). Untere konvexe Huelle der Tiefs vom Anker bis zum letzten
bestaetigten Swing-Tief (PIVOT Tage links und rechts). Das letzte Huellensegment, nach rechts verlaengert, ist die
"Action-Linie". Kein Tief zwischen den Beruehrungspunkten liegt darunter. Berechnung im Log-Preis.
Einstieg: Tief des Tages <= Linie*(1+Toleranz) und Schluss > Linie, Kauf zum Eroeffnungskurs des Folgetags.
Ausstieg A ("linie"): Schlusskurs unter der Linie (Linie bleibt die vom Einstiegstag), Verkauf zum naechsten Eroeffnungskurs.
Ausstieg B ("trail"): zusaetzlich Stop unter dem jeweils letzten bestaetigten Swing-Tief nach dem Einstieg.

Umgebung: TICKER (Standard AAPL), YEARS (Standard 10). Ausgabe: Tabelle im Log und backtest_results.json.
Keine Anlageberatung.
"""
import itertools
import json
import math
import os
import sys

import numpy as np
import pandas as pd

PIVOT = 3
LOOKBACKS = (126, 252, 504)
TOLERANCES = (0.005, 0.01, 0.02)
MIN_POINTS = (2, 3)      # Mindestzahl Beruehrungspunkte (Huellenecken) der Linie
EXITS = ("linie", "trail")


def lower_hull(xs, ys):
    """Untere konvexe Huelle (Monotone Chain) ueber Punkte mit aufsteigendem x. Gibt Indizes der Ecken zurueck."""
    hull = []
    for i in range(len(xs)):
        while len(hull) >= 2:
            a, b = hull[-2], hull[-1]
            cross = (xs[b] - xs[a]) * (ys[i] - ys[a]) - (ys[b] - ys[a]) * (xs[i] - xs[a])
            if cross <= 0:      # b liegt auf oder ueber der Verbindung a-i: keine Ecke der unteren Huelle
                hull.pop()
            else:
                break
        hull.append(i)
    return hull


def support_line(low, t, lookback, min_points):
    """Support-Linie fuer Tag t aus Daten bis t-1. Gibt (Steigung, Achsenabschnitt im Log-Preis, Punktzahl) oder None."""
    end = t - 1                       # letzter bekannter Tag
    start = max(0, end - lookback + 1)
    if end - start < 20:
        return None
    a = start + int(np.argmin(low[start:end + 1]))
    # letztes bestaetigtes Swing-Tief (rechts PIVOT Tage Bestaetigung)
    last = None
    for j in range(end - PIVOT, a, -1):
        if j - PIVOT >= 0 and low[j] <= low[j - PIVOT:j + PIVOT + 1].min():
            last = j
            break
    if last is None or last <= a:
        return None
    xs = np.arange(a, last + 1, dtype=float)
    ys = np.log(low[a:last + 1])
    h = lower_hull(xs, ys)
    if len(h) < 2 or len(h) < min_points:
        return None
    p, q = h[-2], h[-1]
    slope = (ys[q] - ys[p]) / (xs[q] - xs[p])
    if slope <= 0:
        return None
    icpt = ys[q] - slope * xs[q]
    return slope, icpt, len(h)


def simulate(o, h, l, c, lookback, tol, min_points, exit_mode):
    n = len(c)
    trades, t = [], lookback // 4 + 30
    while t < n - 2:
        sl = support_line(l, t, lookback, min_points)
        if sl is None:
            t += 1
            continue
        slope, icpt, pts = sl
        line_t = math.exp(icpt + slope * t)
        if not (c[t] > line_t and l[t] <= line_t * (1 + tol)) or c[t - 1] <= math.exp(icpt + slope * (t - 1)):
            t += 1
            continue
        ei = t + 1
        entry = o[ei]
        stop0 = math.exp(icpt + slope * ei)
        risk = entry - stop0
        if risk <= 0:
            t += 1
            continue
        trail, xi, reason = stop0, None, "ende"
        for j in range(ei, n):
            line_j = math.exp(icpt + slope * j)
            if exit_mode == "trail" and j - PIVOT > ei and l[j - PIVOT] <= l[j - 2 * PIVOT:j + 1].min():
                trail = max(trail, l[j - PIVOT])
            stop = max(line_j, trail) if exit_mode == "trail" else line_j
            if c[j] < stop:
                if j + 1 < n:
                    xi, reason = j + 1, "stop"
                else:
                    xi, reason = j, "ende"
                break
        if xi is None:
            xi = n - 1
        exit_px = o[xi] if reason == "stop" else c[xi]
        trades.append({"ein": ei, "aus": xi, "entry": entry, "exit": exit_px, "risk": risk,
                       "ret": exit_px / entry - 1, "R": (exit_px - entry) / risk, "tage": xi - ei, "punkte": pts})
        t = xi + 1
    return trades


def stats(trades, n_days, bh_ret, bh_dd):
    if not trades:
        return {"trades": 0}
    rets = np.array([x["ret"] for x in trades])
    Rs = np.array([x["R"] for x in trades])
    wins, losses = rets[rets > 0], rets[rets <= 0]
    equity, peak, mdd, curve = 1.0, 1.0, 0.0, 1.0
    for x in trades:
        equity *= 1 + x["ret"]
        peak = max(peak, equity)
        mdd = min(mdd, equity / peak - 1)
    return {
        "trades": len(trades), "trefferquote_pct": round(100 * (rets > 0).mean(), 1),
        "ø_trade_pct": round(100 * rets.mean(), 2), "ø_R": round(float(Rs.mean()), 2),
        "gewinnfaktor": round(float(wins.sum() / -losses.sum()), 2) if len(losses) and losses.sum() < 0 else None,
        "ø_haltedauer_tage": round(float(np.mean([x["tage"] for x in trades])), 1),
        "zeit_im_markt_pct": round(100 * sum(x["tage"] for x in trades) / n_days, 1),
        "gesamt_pct": round(100 * (equity - 1), 1), "max_verlust_pct": round(100 * mdd, 1),
        "buy_hold_pct": round(100 * bh_ret, 1), "buy_hold_max_verlust_pct": round(100 * bh_dd, 1),
    }


def run(df):
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("Open", "High", "Low", "Close"))
    n = len(c)
    bh_ret = c[-1] / c[0] - 1
    bh_dd = float((c / np.maximum.accumulate(c) - 1).min())
    results = []
    for lb, tol, mp, ex in itertools.product(LOOKBACKS, TOLERANCES, MIN_POINTS, EXITS):
        tr = simulate(o, h, l, c, lb, tol, mp, ex)
        s = stats(tr, n, bh_ret, bh_dd)
        s.update({"fenster": lb, "toleranz_pct": tol * 100, "min_punkte": mp, "ausstieg": ex})
        results.append(s)
    return results, bh_ret, bh_dd


def main():
    import yfinance as yf
    ticker = os.environ.get("TICKER", "AAPL").strip().upper()
    years = int(os.environ.get("YEARS", "10"))
    raw = None
    for _ in range(3):
        raw = yf.download(ticker, period="%dy" % years, interval="1d", auto_adjust=True, progress=False, threads=False)
        if raw is not None and not raw.empty:
            break
    if raw is None or raw.empty:
        sys.exit("Fehler: keine Kursdaten fuer " + ticker)
    cols = {}
    for k in ("Open", "High", "Low", "Close"):
        x = raw[k]
        cols[k] = x.iloc[:, 0] if hasattr(x, "columns") else x
    df = pd.DataFrame(cols).dropna()
    results, bh_ret, bh_dd = run(df)
    print("%s: %d Handelstage (%s bis %s). Buy & Hold: %+.1f %%, groesster Rueckgang %.1f %%\n" % (
        ticker, len(df), df.index[0].date(), df.index[-1].date(), 100 * bh_ret, 100 * bh_dd))
    print("Fenster Tol% Pkte Ausstieg | Trades Treffer% oTrade% oR  GewFkt Tage ImMarkt% Gesamt% MaxVerl%")
    for r in sorted(results, key=lambda r: -(r.get("ø_R", -99) if r["trades"] else -99)):
        if not r["trades"]:
            print("%5d %4.1f %4d %-7s | keine Trades" % (r["fenster"], r["toleranz_pct"], r["min_punkte"], r["ausstieg"]))
            continue
        print("%5d %4.1f %4d %-7s | %6d %7.1f %7.2f %5.2f %6s %4.1f %8.1f %7.1f %8.1f" % (
            r["fenster"], r["toleranz_pct"], r["min_punkte"], r["ausstieg"], r["trades"], r["trefferquote_pct"],
            r["ø_trade_pct"], r["ø_R"], r["gewinnfaktor"], r["ø_haltedauer_tage"], r["zeit_im_markt_pct"],
            r["gesamt_pct"], r["max_verlust_pct"]))
    with open("backtest_results.json", "w", encoding="utf-8") as f:
        json.dump({"ticker": ticker, "von": str(df.index[0].date()), "bis": str(df.index[-1].date()),
                   "buy_hold_pct": round(100 * bh_ret, 1), "ergebnisse": results}, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
