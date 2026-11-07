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


SSGA_URL = "https://www.ssga.com/library-content/products/fund-data/etfs/us/navhist-us-en-%s.xlsx"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def ssga_rows(t):
    """Liest die Tageshistorie (Datum, NAV, Anteile) eines SPDR-ETFs von State Street. Neueste Zeile zuerst.
    Gibt [] zurueck, wenn der Fonds dort nicht gefuehrt wird oder der Abruf scheitert."""
    import io
    import urllib.request
    try:
        import openpyxl
        req = urllib.request.Request(SSGA_URL % t.lower(), headers={"User-Agent": UA, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=40) as r:
            data = r.read()
        ws = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True).worksheets[0]
    except Exception:
        return []
    rows = []
    for row in ws.iter_rows(values_only=True):
        if not row or len(row) < 3:
            continue
        try:
            d = datetime.datetime.strptime(str(row[0]).strip(), "%d-%b-%Y").date()
            nav, sh = float(row[1]), float(row[2])
        except (ValueError, TypeError):
            continue
        if nav > 0 and sh > 0:
            rows.append((d, nav, sh))
    rows.sort(key=lambda x: x[0], reverse=True)
    return rows


def flows_from_rows(rows):
    """Netto-Zufluss = Summe der Anteilsveraenderung je Tag mal NAV dieses Tages (Ausgabe und Ruecknahme zum NAV).
    Prozent bezogen auf das Fondsvermoegen am Start. Gibt ausserdem das Datum der letzten Zeile zurueck."""
    out = {}
    for n in (1, 5, 21):
        if len(rows) < n + 2:
            continue
        flow = sum((rows[i][2] - rows[i + 1][2]) * rows[i][1] for i in range(n))
        start = rows[n][2] * rows[n][1]
        out["f%d" % n] = clean(flow / 1e6, 0)
        out["fp%d" % n] = clean(flow / start * 100)
    return out, (rows[0][0].isoformat() if rows else None)


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

    out_sectors, missing, last_date, flow_dates = {}, [], None, []
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
                fl, fdate = flows_from_rows(ssga_rows(t))
                if fl:
                    item.update(fl)
                    flow_dates.append(fdate)
            items.append(item)
        if any(i["kind"] == "sector" for i in items):
            out_sectors[sec] = {"name": cfg["name"], "items": items}

    if not out_sectors:
        sys.exit("Fehler: keine Sektordaten verfuegbar.")

    out = {
        "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": last_date,
        "flow_date": max(flow_dates) if flow_dates else None,
        "sectors": out_sectors,
    }
    with open("details.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("OK: %d Sektoren, %d Werte, fehlend: %s" % (
        len(out_sectors), sum(len(s["items"]) for s in out_sectors.values()), ", ".join(missing) or "keine"))


if __name__ == "__main__":
    main()
