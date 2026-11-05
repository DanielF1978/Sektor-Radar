"""Testlauf: Was liefert Yahoo Finance an Anteilszahlen (Shares Outstanding) fuer die Sektor-ETFs?
Schreibt nur ins Log, veraendert nichts im Repo. Daraus ergibt sich, ob sich Zufluesse
(Aenderung der Anteile mal Kurs) damit verlaesslich berechnen lassen."""
import datetime

import yfinance as yf

ETFS = ["XLK", "XLC", "XLY", "XLP", "XLF", "XLV", "XLI", "XLE", "XLB", "XLU", "XLRE", "SPY"]
start = (datetime.date.today() - datetime.timedelta(days=120)).isoformat()

for t in ETFS:
    print("=" * 60)
    print(t)
    tk = yf.Ticker(t)
    try:
        s = tk.get_shares_full(start=start)
        if s is None or len(s) == 0:
            print("  get_shares_full: leer")
        else:
            s = s[~s.index.duplicated(keep="last")]
            print("  get_shares_full: %d Werte, %s bis %s, %d verschiedene Werte"
                  % (len(s), s.index[0].date(), s.index[-1].date(), s.nunique()))
            for d, v in list(s.tail(6).items()):
                print("    %s  %s" % (d.date(), f"{int(v):,}"))
    except Exception as e:
        print("  get_shares_full Fehler: %s: %s" % (type(e).__name__, str(e)[:120]))
    try:
        info = tk.info
        print("  info: sharesOutstanding=%s totalAssets=%s navPrice=%s"
              % (info.get("sharesOutstanding"), info.get("totalAssets"), info.get("navPrice")))
    except Exception as e:
        print("  info Fehler: %s: %s" % (type(e).__name__, str(e)[:120]))
