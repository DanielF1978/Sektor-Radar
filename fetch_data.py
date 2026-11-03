"""Holt Tageskurse der 11 Sektor-ETFs und des S&P 500 (SPY) und schreibt data.json."""
import datetime
import json
import sys

import yfinance as yf

TICKERS = ["SPY", "XLK", "XLF", "XLY", "XLC", "XLI", "XLB", "XLE", "XLV", "XLP", "XLU", "XLRE"]

raw = yf.download(TICKERS, period="2y", interval="1d", auto_adjust=True, progress=False)
if raw is None or raw.empty:
    sys.exit("Fehler: Yahoo Finance hat keine Daten geliefert.")

close = raw["Close"]
missing = [t for t in TICKERS if t not in close.columns or close[t].dropna().empty]
if missing:
    sys.exit("Fehler: keine Daten fuer " + ", ".join(missing))

close = close[TICKERS].dropna()
if len(close) < 150:
    sys.exit("Fehler: zu wenige Handelstage (" + str(len(close)) + ")")

out = {
    "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "dates": [d.strftime("%Y-%m-%d") for d in close.index],
    "series": {t: [round(float(x), 4) for x in close[t].tolist()] for t in TICKERS},
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(out, f, separators=(",", ":"))

print("OK:", len(out["dates"]), "Tage, letzter Handelstag", out["dates"][-1])
