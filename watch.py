"""Eigene Beobachtungsliste: meldet per ntfy, wenn der Kurs unter bzw. wieder ueber seinen gleitenden
Durchschnitt (z. B. 150 Tage) faellt.

Die Werte stehen in watchlist.json (Ticker so, wie Yahoo Finance sie fuehrt, z. B. AAPL, SPY, VWCE.DE, EUNL.DE).
  "ma"         Laenge des Durchschnitts in Handelstagen (Standard 150)
  "margin_pct" Pufferzone um die Linie in Prozent, gegen staendiges Hin und Her (Standard 0,5)
Ein Wechsel gilt erst, wenn der Schlusskurs die Linie um mehr als den Puffer durchbricht.

Umgebungsvariablen: NTFY_TOPIC, DRY_RUN=1 (nur ausgeben). Stand: watch_state.json
Der erste Lauf je Wert speichert nur den Zustand und meldet nichts (eine Uebersicht ausgenommen).
"""
import json
import os
import sys
import time
import urllib.request

import pandas as pd
import yfinance as yf

SITE = "https://danielf1978.github.io/Sektor-Radar/"
STATE = "watch_state.json"


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def send(topic, title, body, priority, tags):
    if os.environ.get("DRY_RUN") == "1":
        print("[DRY_RUN] %s | prio %s | %s\n%s\n" % (title, priority, tags, body))
        return
    req = urllib.request.Request("https://ntfy.sh/" + topic, data=body.encode("utf-8"),
                                 headers={"Title": title.encode("utf-8"), "Priority": str(priority),
                                          "Tags": tags, "Click": SITE}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


def closes(ticker):
    """Gibt ein DataFrame mit Open, High, Low, Close zurueck (oder None)."""
    for _ in range(3):
        try:
            df = yf.download(ticker, period="2y", interval="1d", auto_adjust=False, progress=False, threads=False)
            if df is not None and not df.empty:
                cols = {}
                for f in ("Open", "High", "Low", "Close"):
                    c = df[f]
                    if hasattr(c, "columns"):
                        c = c.iloc[:, 0]
                    cols[f] = c
                out = pd.DataFrame(cols).dropna()
                if len(out):
                    return out
        except Exception as e:
            print("%s: %s" % (ticker, e))
        time.sleep(4)
    return None


def main():
    cfg = load("watchlist.json", {"werte": []})
    margin = float(cfg.get("margin_pct", 0.5)) / 100
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    dry = os.environ.get("DRY_RUN") == "1"
    if not topic and not dry:
        print("Hinweis: NTFY_TOPIC fehlt, keine Meldung, Stand bleibt unveraendert.")
        return
    state = load(STATE, {})
    new_state, summary, items = {}, [], []
    for w in cfg.get("werte", []):
        t, n = str(w["t"]).strip().upper(), int(w.get("ma", 150))
        label = w.get("name") or t
        ohlc = closes(t)
        c = ohlc["Close"] if ohlc is not None else None
        if c is None or len(c) < n + 5:
            print("%s: zu wenige Daten, uebersprungen" % t)
            items.append({"t": t, "name": label, "ma": n, "error": "Keine oder zu wenige Kursdaten bei Yahoo Finance gefunden"})
            if t + "|" + str(n) in state:
                new_state[t + "|" + str(n)] = state[t + "|" + str(n)]
            continue
        key = "%s|%d" % (t, n)
        ma_s = c.rolling(n).mean()
        px, ma = float(c.iloc[-1]), float(ma_s.iloc[-1])
        dist = (px / ma - 1) * 100
        day = c.index[-1].strftime("%d.%m.%Y")
        old = state.get(key, {}).get("pos")
        pos = old
        if px < ma * (1 - margin):
            pos = "below"
        elif px > ma * (1 + margin):
            pos = "above"
        elif old is None:
            pos = "below" if px < ma else "above"
        new_state[key] = {"pos": pos, "px": round(px, 2), "ma": round(ma, 2), "day": day}
        tail = 250
        items.append({"t": t, "name": label, "ma": n, "pos": pos, "px": round(px, 2), "mav": round(ma, 2),
                      "dist": round(dist, 2), "day": c.index[-1].strftime("%Y-%m-%d"),
                      "c": [round(float(x), 2) for x in c.tail(tail)],
                      "m": [None if x != x else round(float(x), 2) for x in ma_s.tail(tail)]})
        K = 300
        r2 = lambda ser: [None if x != x else round(float(x), 2) for x in ser.tail(K)]
        items[-1]["k"] = {"d": [d.strftime("%Y-%m-%d") for d in c.index[-K:]], "o": r2(ohlc["Open"]), "h": r2(ohlc["High"]),
                          "l": r2(ohlc["Low"]), "c": r2(c), "s50": r2(c.rolling(50).mean()),
                          "s150": r2(c.rolling(150).mean()), "s200": r2(c.rolling(200).mean())}
        txt = "Kurs %.2f, %d-Tage-Linie %.2f (%+.1f %%), Stand %s" % (px, n, ma, dist, day)
        summary.append("%s: %s" % (label, txt))
        print("%s -> %s | %s" % (key, pos, txt))
        if old and pos != old:
            if pos == "below":
                send(topic, "%s fällt unter die %d-Tage-Linie" % (label, n), txt, 4, "chart_with_downwards_trend")
            else:
                send(topic, "%s steigt wieder über die %d-Tage-Linie" % (label, n), txt, 3, "chart_with_upwards_trend")
        elif state and key not in state:
            send(topic, "%s zur Beobachtungsliste hinzugefügt" % label,
                 txt + (" – aktuell darunter" if pos == "below" else " – aktuell darüber"), 2, "eyes")
    if not state and summary:
        send(topic, "Beobachtungsliste eingerichtet", "\n".join(summary), 3, "eyes")
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(new_state, f, sort_keys=True, indent=1)
    import datetime
    with open("watch_data.json", "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "margin_pct": margin * 100, "items": items}, f, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
