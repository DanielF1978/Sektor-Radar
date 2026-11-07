"""Branchen-Radar: findet die Branchen (GICS-Sub-Industries), die in dieser Woche bullish geworden sind.

Ablauf:
  1. Aktienliste aus Wikipedia (S&P 500, 400, 600) mit Sektor und Sub-Industry. Bei Fehler: letzte gespeicherte Liste.
  2. Kurse der letzten 12 Monate von Yahoo Finance.
  3. Pro Branche ein gleichgewichteter Index aus allen Mitgliedern.
  4. Einstufung:
       neu      = jetzt ueber 50- UND 150-Tage-Linie, vor 5 Handelstagen noch nicht
       frueh    = jetzt ueber der 50-Tage-Linie, vor 5 Handelstagen darunter, aber noch unter der 150-Tage-Linie
       bullish  = war schon vorher ueber beiden Linien
       bearish  = sonst
     Branchen mit weniger als MIN_MEMBERS Aktien werden ausgeblendet.
Ausgabe: industries.json (fuer die Seite), industries_universe.json (Zwischenspeicher der Aktienliste).
Optional: NTFY_TOPIC (Meldung per ntfy), DRY_RUN=1 (Meldung nur ausgeben).
"""
import datetime
import io
import json
import os
import sys
import time
import urllib.request

import pandas as pd
import yfinance as yf

MIN_MEMBERS = 4
LOOKBACK = 5                 # Handelstage = eine Woche
SITE = "https://danielf1978.github.io/Sektor-Radar/"
UNIVERSE_FILE = "industries_universe.json"
PAGES = ["List_of_S%26P_500_companies", "List_of_S%26P_400_companies", "List_of_S%26P_600_companies"]
UA = "Sektor-Radar (privates Projekt, https://github.com/DanielF1978/Sektor-Radar)"


def wiki_tables(page):
    req = urllib.request.Request("https://en.wikipedia.org/wiki/" + page, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        html = r.read().decode("utf-8", errors="replace")
    return pd.read_html(io.StringIO(html))


def parse_universe_table(df):
    """Gibt {Ticker: (Name, Sektor, Branche)} zurueck, wenn die Tabelle die passenden Spalten hat, sonst {}."""
    cols = {str(c): c for c in df.columns}
    def find(*keys, exclude=()):
        for k, c in cols.items():
            lk = k.lower()
            if all(x in lk for x in keys) and not any(x in lk for x in exclude):
                return c
        return None
    sym = find("symbol") or find("ticker")
    sub = find("sub-industry") or find("sub industry")
    sec = find("sector", exclude=("sub",))
    name = find("security") or find("company")
    if sym is None or sub is None:
        return {}
    out = {}
    for _, row in df.iterrows():
        t = str(row[sym]).strip().replace(".", "-")
        s = str(row[sub]).strip()
        if not t or t == "nan" or not s or s == "nan":
            continue
        out[t] = (str(row[name]).strip() if name is not None else t,
                  str(row[sec]).strip() if sec is not None else "", s)
    return out


def load_universe():
    uni = {}
    try:
        for page in PAGES:
            got = {}
            for tbl in wiki_tables(page):
                got = parse_universe_table(tbl)
                if len(got) > 100:
                    break
            print("%s: %d Werte" % (page, len(got)))
            uni.update(got)
        if len(uni) > 800:
            with open(UNIVERSE_FILE, "w", encoding="utf-8") as f:
                json.dump(uni, f, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            return uni
        print("Wikipedia lieferte zu wenige Werte (%d), nutze Zwischenspeicher." % len(uni))
    except Exception as e:
        print("Wikipedia nicht lesbar (%s), nutze Zwischenspeicher." % e)
    try:
        with open(UNIVERSE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def download_closes(tickers, chunk=150):
    frames = []
    for i in range(0, len(tickers), chunk):
        part = tickers[i:i + chunk]
        raw = None
        for _ in range(3):
            try:
                raw = yf.download(part, period="1y", interval="1d", auto_adjust=True, progress=False, threads=False)
                if raw is not None and not raw.empty:
                    break
            except Exception as e:
                print("Download-Fehler: %s" % e)
            time.sleep(5)
        if raw is None or raw.empty:
            print("Abschnitt %d-%d ohne Daten" % (i, i + len(part)))
            continue
        c = raw["Close"]
        if isinstance(c, pd.Series):
            c = c.to_frame(part[0])
        frames.append(c)
        print("Kurse geladen: %d/%d" % (min(i + chunk, len(tickers)), len(tickers)))
    if not frames:
        return None
    close = pd.concat(frames, axis=1)
    close = close.loc[:, ~close.columns.duplicated()]
    return close.dropna(axis=1, how="all").sort_index()


def build(close, uni):
    """Berechnet die Branchenkennzahlen. close: Schlusskurse (Spalten = Ticker), uni: {Ticker: (Name, Sektor, Branche)}."""
    rets = close.pct_change(fill_method=None)
    sma50 = close.rolling(50).mean()
    last = close.iloc[-1]
    ago = close.iloc[-1 - LOOKBACK]
    m1 = close.iloc[-22] if len(close) > 22 else None
    groups = {}
    for t in close.columns:
        if t in uni:
            groups.setdefault(uni[t][2], []).append(t)
    items = []
    for ind, members in groups.items():
        if len(members) < MIN_MEMBERS:
            continue
        idx = (1 + rets[members].mean(axis=1).fillna(0)).cumprod()
        if len(idx) < 160:
            continue
        s50, s150 = idx.rolling(50).mean(), idx.rolling(150).mean()
        now50, now150 = idx.iloc[-1] > s50.iloc[-1], idx.iloc[-1] > s150.iloc[-1]
        p50, p150 = idx.iloc[-1 - LOOKBACK] > s50.iloc[-1 - LOOKBACK], idx.iloc[-1 - LOOKBACK] > s150.iloc[-1 - LOOKBACK]
        bull_now, bull_prev = bool(now50 and now150), bool(p50 and p150)
        if bull_now and not bull_prev:
            status = "neu"
        elif bool(now50) and not bool(p50) and not bull_now:
            status = "frueh"
        elif bull_now:
            status = "bullish"
        else:
            status = "bearish"
        valid = [t for t in members if sma50[t].iloc[-1] == sma50[t].iloc[-1]]
        breadth = round(100 * sum(1 for t in valid if last[t] > sma50[t].iloc[-1]) / len(valid)) if valid else None
        mem = []
        for t in members:
            r5 = last[t] / ago[t] - 1 if ago[t] == ago[t] and ago[t] else None
            mem.append([t, uni[t][0], None if r5 is None or r5 != r5 else round(float(r5) * 100, 1)])
        mem.sort(key=lambda x: (x[2] is None, -(x[2] or 0)))
        sectors = [uni[t][1] for t in members]
        items.append({
            "name": ind, "sector": max(set(sectors), key=sectors.count), "n": len(members), "status": status,
            "r5": round(float(idx.iloc[-1] / idx.iloc[-1 - LOOKBACK] - 1) * 100, 1),
            "r21": round(float(idx.iloc[-1] / idx.iloc[-22] - 1) * 100, 1),
            "br": breadth, "m": mem[:12],
        })
    items.sort(key=lambda x: -x["r5"])
    counts = {"total": len(items)}
    for s in ("neu", "frueh", "bullish", "bearish"):
        counts[s] = sum(1 for x in items if x["status"] == s)
    counts["bull_all"] = counts["neu"] + counts["bullish"]
    return items, counts


def send(topic, title, body, priority, tags):
    if os.environ.get("DRY_RUN") == "1":
        print("[DRY_RUN] %s | prio %s | %s\n%s\n" % (title, priority, tags, body))
        return
    req = urllib.request.Request("https://ntfy.sh/" + topic, data=body.encode("utf-8"),
                                 headers={"Title": title.encode("utf-8"), "Priority": str(priority),
                                          "Tags": tags, "Click": SITE}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


def notify(items, counts, date):
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic and os.environ.get("DRY_RUN") != "1":
        print("Hinweis: NTFY_TOPIC fehlt, keine Meldung.")
        return
    neu = [x for x in items if x["status"] == "neu"]
    frueh = [x for x in items if x["status"] == "frueh"]
    lines = []
    if neu:
        lines.append("Neu bullish: " + "; ".join("%s (%+.1f %%, %s %% der Aktien über 50 T)" % (x["name"], x["r5"], x["br"]) for x in neu[:8]))
    else:
        lines.append("Diese Woche ist keine Branche neu bullish geworden.")
    if frueh:
        lines.append("Frühe Dreher: " + "; ".join("%s (%+.1f %%)" % (x["name"], x["r5"]) for x in frueh[:6]) + (" …" if len(frueh) > 6 else ""))
    lines.append("Insgesamt bullish: %d von %d Branchen." % (counts["bull_all"], counts["total"]))
    send(topic, "Branchen-Radar: %d neu bullish" % len(neu), "\n".join(lines), 4 if neu else 3, "seedling" if neu else "eyes")


def main():
    uni = load_universe()
    if len(uni) < 300:
        sys.exit("Fehler: keine Aktienliste verfuegbar.")
    close = download_closes(sorted(uni))
    if close is None or len(close) < 170:
        sys.exit("Fehler: zu wenige Kursdaten.")
    items, counts = build(close, uni)
    if not items:
        sys.exit("Fehler: keine Branchen berechnet.")
    date = close.index[-1].strftime("%Y-%m-%d")
    out = {"updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "date": date, "min_members": MIN_MEMBERS, "counts": counts, "items": items}
    with open("industries.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("OK: %d Branchen, neu bullish %d, fruehe Dreher %d, insgesamt bullish %d (Stand %s, %d Aktien mit Kursen)" % (
        counts["total"], counts["neu"], counts["frueh"], counts["bull_all"], date, close.shape[1]))
    notify(items, counts, date)


if __name__ == "__main__":
    main()
