"""Holt Kurse und Volumen von Sektor-ETFs, Teilbranchen-ETFs und den groessten Einzelwerten
und schreibt details.json (Kennzahlen fuer die Detailansicht).

Die Listen unten sind eine Auswahl der groessten Werte je Sektor. Sie koennen von Hand
angepasst werden (Ticker so, wie Yahoo Finance sie fuehrt, z. B. BRK-B).
"""
import datetime
import json
import os
import sys
import time

import pandas as pd
import yfinance as yf

SECTORS = {
    "XLK": {"name": "Technologie",
            "subs": [("SMH", "Halbleiter (ETF)"), ("IGV", "Software (ETF)")],
            "stocks": [("NVDA", "NVIDIA"), ("AAPL", "Apple"), ("MSFT", "Microsoft"), ("AVGO", "Broadcom"),
                       ("ORCL", "Oracle"), ("AMD", "AMD"), ("CRM", "Salesforce"), ("CSCO", "Cisco")]},
    "XLC": {"name": "Kommunikation", "subs": [],
            "stocks": [("META", "Meta"), ("GOOGL", "Alphabet"), ("NFLX", "Netflix"), ("DIS", "Disney"),
                       ("T", "AT&T"), ("VZ", "Verizon"), ("TMUS", "T-Mobile US"), ("CMCSA", "Comcast")]},
    "XLY": {"name": "Zyklischer Konsum",
            "subs": [("XHB", "Wohnbau (ETF)"), ("XRT", "Einzelhandel (ETF)")],
            "stocks": [("AMZN", "Amazon"), ("TSLA", "Tesla"), ("HD", "Home Depot"), ("MCD", "McDonald's"),
                       ("BKNG", "Booking"), ("LOW", "Lowe's"), ("TJX", "TJX"), ("SBUX", "Starbucks")]},
    "XLP": {"name": "Basiskonsumgüter", "subs": [],
            "stocks": [("WMT", "Walmart"), ("COST", "Costco"), ("PG", "Procter & Gamble"), ("KO", "Coca-Cola"),
                       ("PEP", "PepsiCo"), ("PM", "Philip Morris"), ("MDLZ", "Mondelez"), ("MO", "Altria")]},
    "XLF": {"name": "Finanzwesen",
            "subs": [("KBE", "Banken (ETF)"), ("KRE", "Regionalbanken (ETF)"), ("KIE", "Versicherer (ETF)")],
            "stocks": [("BRK-B", "Berkshire Hathaway"), ("JPM", "JPMorgan"), ("V", "Visa"), ("MA", "Mastercard"),
                       ("BAC", "Bank of America"), ("WFC", "Wells Fargo"), ("GS", "Goldman Sachs"), ("MS", "Morgan Stanley")]},
    "XLV": {"name": "Gesundheitswesen",
            "subs": [("XBI", "Biotech gleichgewichtet (ETF)"), ("IBB", "Biotech (ETF)"), ("XPH", "Pharma (ETF)"),
                     ("IHI", "Medizintechnik (ETF)"), ("IHF", "Gesundheitsdienstleister (ETF)")],
            "stocks": [("LLY", "Eli Lilly"), ("JNJ", "Johnson & Johnson"), ("ABBV", "AbbVie"), ("UNH", "UnitedHealth"),
                       ("MRK", "Merck"), ("ABT", "Abbott"), ("TMO", "Thermo Fisher"), ("ISRG", "Intuitive Surgical")]},
    "XLI": {"name": "Industrie",
            "subs": [("ITA", "Luft- und Raumfahrt, Rüstung (ETF)"), ("IYT", "Transport (ETF)")],
            "stocks": [("GE", "GE Aerospace"), ("CAT", "Caterpillar"), ("RTX", "RTX"), ("UNP", "Union Pacific"),
                       ("HON", "Honeywell"), ("BA", "Boeing"), ("DE", "Deere"), ("ETN", "Eaton")]},
    "XLE": {"name": "Energie",
            "subs": [("XOP", "Öl- und Gasförderung (ETF)"), ("OIH", "Ölservice (ETF)")],
            "stocks": [("XOM", "Exxon Mobil"), ("CVX", "Chevron"), ("COP", "ConocoPhillips"), ("WMB", "Williams"),
                       ("EOG", "EOG Resources"), ("SLB", "SLB"), ("KMI", "Kinder Morgan"), ("PSX", "Phillips 66")]},
    "XLB": {"name": "Materialien",
            "subs": [("GDX", "Goldminen (ETF)"), ("XME", "Metalle und Bergbau (ETF)")],
            "stocks": [("LIN", "Linde"), ("SHW", "Sherwin-Williams"), ("FCX", "Freeport-McMoRan"), ("ECL", "Ecolab"),
                       ("APD", "Air Products"), ("NEM", "Newmont"), ("CTVA", "Corteva"), ("NUE", "Nucor")]},
    "XLU": {"name": "Versorger", "subs": [],
            "stocks": [("NEE", "NextEra Energy"), ("SO", "Southern Company"), ("DUK", "Duke Energy"), ("CEG", "Constellation Energy"),
                       ("AEP", "American Electric Power"), ("SRE", "Sempra"), ("D", "Dominion Energy"), ("VST", "Vistra")]},
    "XLRE": {"name": "Immobilien", "subs": [],
             "stocks": [("PLD", "Prologis"), ("AMT", "American Tower"), ("EQIX", "Equinix"), ("WELL", "Welltower"),
                        ("SPG", "Simon Property"), ("PSA", "Public Storage"), ("O", "Realty Income"), ("DLR", "Digital Realty")]},
}


def clean(x, d=2):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if x != x or x in (float("inf"), float("-inf")):
        return None
    return round(x, d)


def metrics(df):
    """df: Spalten c, h, l, v (Schlusskurs, Hoch, Tief, Volumen), aufsteigend nach Datum."""
    if len(df) < 45:
        return None
    c, h, l, v = df["c"], df["h"], df["l"], df["v"]
    out = {}
    for n in (1, 5, 21):
        out["r%d" % n] = clean((c.iloc[-1] / c.iloc[-1 - n] - 1) * 100)
        prev = v.iloc[-n - 20:-n].mean()
        out["rv%d" % n] = clean(v.iloc[-n:].mean() / prev) if prev > 0 else None
    d = c.diff().tail(20)
    vv = v.tail(20)
    up, dn = vv[d > 0].sum(), vv[d < 0].sum()
    out["udv"] = clean(up / dn) if dn > 0 else None
    rng = (h - l).tail(20)
    mfm = (((c - l) - (h - c)).tail(20) / rng.where(rng > 0)).fillna(0)
    out["cmf"] = clean((mfm * vv).sum() / vv.sum()) if vv.sum() > 0 else None
    out["dv"] = clean((c * v).tail(20).mean() / 1e6, 0)
    return out


SNAP_FILE = "fund_snapshots.json"
SNAP_KEEP = 150          # Tage Historie
NAV_TOLERANCE = 0.03     # NAV-Veraenderung und Kursveraenderung duerfen hoechstens so weit abweichen


def load_snaps():
    try:
        with open(SNAP_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def take_snapshot(t, snaps, key):
    """Speichert Fondsvermoegen und Nettoinventarwert von heute. Yahoo liefert keine Historie dafuer,
    deshalb baut sich die Datenbasis Tag fuer Tag auf."""
    try:
        info = yf.Ticker(t).info
        ta, nav = info.get("totalAssets"), info.get("navPrice")
    except Exception:
        return
    if not ta or not nav:
        return
    snaps.setdefault(t, {})[key] = {"ta": int(ta), "nav": round(float(nav), 4)}


def snap_flows(t, df, snaps):
    """Geschaetzter Netto-Zufluss = Fondsvermoegen heute minus Fondsvermoegen am Start, hochgerechnet mit der
    Wertentwicklung des Fonds. Wird nur berechnet, wenn die Daten plausibel und frisch sind."""
    h = snaps.get(t, {})
    keys = sorted(h)
    if len(keys) < 2:
        return {}
    end_key = keys[-1]
    last_day = df.index[-1].date()
    if abs((last_day - datetime.date.fromisoformat(end_key)).days) > 3:
        return {}
    if h[end_key]["ta"] == h[keys[-2]]["ta"]:    # Fondsvermoegen heute unveraendert: vermutlich nicht aktualisiert
        return {}
    out = {}
    for n in (1, 5, 21):
        start_day = df.index[-1 - n].date()
        cand = [k for k in keys if k <= start_day.isoformat()]
        if not cand:
            continue
        start_key = cand[-1]
        if (start_day - datetime.date.fromisoformat(start_key)).days > 4:
            continue
        a, b = h[start_key], h[end_key]
        nav_ratio = b["nav"] / a["nav"]
        px_ratio = float(df["c"].iloc[-1] / df["c"].iloc[-1 - n])
        if abs(nav_ratio / px_ratio - 1) > NAV_TOLERANCE:   # Split, veraltete oder unpassende Werte
            continue
        flow = b["ta"] - a["ta"] * nav_ratio
        out["f%d" % n] = clean(flow / 1e6, 0)
        out["fp%d" % n] = clean(flow / a["ta"] * 100)
    return out


def main():
    tickers = []
    for sec, cfg in SECTORS.items():
        tickers += [sec] + [t for t, _ in cfg["subs"]] + [t for t, _ in cfg["stocks"]]
    tickers = list(dict.fromkeys(tickers))

    raw = None
    for attempt in range(3):
        raw = yf.download(tickers, period="6mo", interval="1d", auto_adjust=True, progress=False, threads=False)
        if raw is not None and not raw.empty:
            break
        time.sleep(5)
    if raw is None or raw.empty:
        sys.exit("Fehler: Yahoo Finance hat keine Daten geliefert.")

    snaps = load_snaps()
    snap_key = os.environ.get("SNAP_DATE") or datetime.date.today().isoformat()   # SNAP_DATE nur fuer Tests
    out_sectors, missing, last_date = {}, [], None
    for sec, cfg in SECTORS.items():
        entries = [(sec, cfg["name"] + " (Sektor-ETF)", "sector")]
        entries += [(t, n, "sub") for t, n in cfg["subs"]]
        entries += [(t, n, "stock") for t, n in cfg["stocks"]]
        items = []
        for t, name, kind in entries:
            try:
                df = pd.DataFrame({"c": raw["Close"][t], "h": raw["High"][t],
                                   "l": raw["Low"][t], "v": raw["Volume"][t]}).dropna()
            except KeyError:
                missing.append(t)
                continue
            m = metrics(df)
            if m is None:
                missing.append(t)
                continue
            last_date = df.index[-1].strftime("%Y-%m-%d")
            item = {"t": t, "name": name, "kind": kind}
            item.update(m)
            if kind in ("sector", "sub"):
                take_snapshot(t, snaps, snap_key)
                item.update(snap_flows(t, df, snaps))
            items.append(item)
        if any(i["kind"] == "sector" for i in items):
            out_sectors[sec] = {"name": cfg["name"], "items": items}

    if not out_sectors:
        sys.exit("Fehler: keine Sektordaten verfuegbar.")

    out = {
        "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": last_date,
        "sectors": out_sectors,
    }
    cut = (datetime.date.fromisoformat(snap_key) - datetime.timedelta(days=SNAP_KEEP)).isoformat()
    for t in list(snaps):
        snaps[t] = {k: v for k, v in snaps[t].items() if k >= cut}
    with open(SNAP_FILE, "w", encoding="utf-8") as f:
        json.dump(snaps, f, sort_keys=True, separators=(",", ":"))
    with open("details.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("OK: %d Sektoren, %d Werte, fehlend: %s" % (
        len(out_sectors), sum(len(s["items"]) for s in out_sectors.values()), ", ".join(missing) or "keine"))


if __name__ == "__main__":
    main()
