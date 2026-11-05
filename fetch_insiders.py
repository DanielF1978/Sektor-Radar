"""Holt Insider-Kaeufe und -Verkaeufe (SEC Form 4) der groessten Einzelwerte je Sektor.

Ausgabe:
  insiders.json        fuer die Seite (Transaktionen, 12 Monate Kurse)
  insiders_state.json  interner Stand (bereits gelesene Meldungen), damit nicht jedes Mal alles neu geladen wird

Benoetigt die Umgebungsvariable SEC_USER_AGENT mit Name und Kontaktadresse, z. B.
  "Sektor-Radar privat name@beispiel.de"
Die SEC verlangt das bei automatisierten Abrufen und erlaubt hoechstens 10 Anfragen pro Sekunde.

Optional: INSIDER_BUDGET_MIN (Zeitbudget je Lauf in Minuten, Standard 30). Ist es aufgebraucht,
wird der Stand gespeichert und beim naechsten Lauf fortgesetzt.
"""
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

LOOKBACK_DAYS = 365
MIN_BUY_VALUE = 1000      # Kaeufe darunter werden ignoriert
MIN_SELL_VALUE = 25000    # Verkaeufe darunter werden ignoriert (viele kleine Steuer-/Planverkaeufe)
PAUSE = 0.15              # Sekunden zwischen Anfragen (ca. 6 pro Sekunde, Limit der SEC: 10)

UA = os.environ.get("SEC_USER_AGENT", "").strip()


def http_get(url):
    """Gibt Bytes zurueck, bei 404 None."""
    last = None
    for attempt in range(4):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            time.sleep(PAUSE)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            last = e
            if e.code in (403, 429, 503) and attempt < 3:
                time.sleep(3 + attempt * 5)
                continue
            raise
        except urllib.error.URLError as e:
            last = e
            if attempt < 3:
                time.sleep(3)
                continue
            raise
    raise last


def _txt(el, path):
    if el is None:
        return None
    v = el.findtext(path)
    return v.strip() if v and v.strip() else None


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def pretty(name):
    return name.title() if name.isupper() else name


def parse_form4(xml_bytes):
    """Liest eine Form-4-Meldung. Gibt Kaeufe (Code P) und Verkaeufe (Code S) am offenen Markt zurueck,
    je Tag und Richtung zusammengefasst."""
    root = ET.fromstring(xml_bytes)
    plan = (root.findtext("aff10b5One") or "").strip().lower() in ("1", "true")
    owner = root.find("reportingOwner")
    name = pretty(_txt(owner, "reportingOwnerId/rptOwnerName") or "Unbekannt")
    rel = owner.find("reportingOwnerRelationship") if owner is not None else None
    parts = []
    if rel is not None:
        title = _txt(rel, "officerTitle")
        if _txt(rel, "isOfficer") in ("1", "true"):
            parts.append(title or "Officer")
        if _txt(rel, "isDirector") in ("1", "true"):
            parts.append("Director")
        if _txt(rel, "isTenPercentOwner") in ("1", "true"):
            parts.append("10 %-Eigner")
        if not parts and (_txt(rel, "isOther") in ("1", "true") or title):
            parts.append(title or "Sonstige")
    role = ", ".join(parts)[:48]

    agg = {}
    for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        code = _txt(tx, "transactionCoding/transactionCode")
        if code not in ("P", "S"):
            continue
        date = _txt(tx, "transactionDate/value")
        shares = _num(_txt(tx, "transactionAmounts/transactionShares/value"))
        price = _num(_txt(tx, "transactionAmounts/transactionPricePerShare/value"))
        if not date or not shares or not price:
            continue
        key = (date[:10], "B" if code == "P" else "S")
        s, v = agg.get(key, (0.0, 0.0))
        agg[key] = (s + shares, v + shares * price)

    out = []
    for (d, a), (s, v) in agg.items():
        if v < (MIN_BUY_VALUE if a == "B" else MIN_SELL_VALUE):
            continue
        out.append({"d": d, "n": name, "r": role, "a": a, "s": int(round(s)),
                    "p": round(v / s, 2), "v": int(round(v)), "pl": 1 if plan else 0})
    return out


def process_ticker(cik, entry, get, cutoff, deadline):
    """Liest neue Form-4-Meldungen eines Unternehmens in entry ein. True, wenn alles abgearbeitet ist."""
    raw = get("https://data.sec.gov/submissions/CIK%010d.json" % cik)
    if raw is None:
        return False
    rec = json.loads(raw)["filings"]["recent"]
    todo = []
    for acc, fd, form, doc in zip(rec["accessionNumber"], rec["filingDate"], rec["form"], rec["primaryDocument"]):
        if form == "4" and fd >= cutoff and acc not in entry["seen"]:
            todo.append((acc, fd, doc))
    complete = True
    for acc, fd, doc in todo:
        if time.time() > deadline:
            complete = False
            break
        fname = doc.split("/")[-1]
        if not fname.lower().endswith(".xml"):
            entry["seen"][acc] = fd
            continue
        url = "https://www.sec.gov/Archives/edgar/data/%d/%s/%s" % (cik, acc.replace("-", ""), fname)
        try:
            data = get(url)
        except Exception as e:  # beim naechsten Lauf erneut versuchen
            print("  Fehler bei %s: %s" % (acc, e))
            complete = False
            continue
        if data is not None:
            try:
                entry["tx"].extend(parse_form4(data))
            except ET.ParseError:
                pass
        entry["seen"][acc] = fd
    entry["seen"] = {a: d for a, d in entry["seen"].items() if d >= cutoff}
    entry["tx"] = sorted([x for x in entry["tx"] if x["d"] >= cutoff], key=lambda x: x["d"], reverse=True)
    return complete


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def fetch_prices(tickers):
    """12 Monate Schlusskurse (fuer den Chart). Gibt (Daten, {Ticker: Werte}) zurueck, bei Fehler leer."""
    try:
        import yfinance as yf
        raw = yf.download(tickers, period="1y", interval="1d", auto_adjust=True, progress=False, threads=False)
        close = raw["Close"]
        dates = [d.strftime("%Y-%m-%d") for d in close.index]
        px = {}
        for t in tickers:
            if t in close.columns:
                px[t] = [None if v != v else round(float(v), 2) for v in close[t].tolist()]
        return dates, px
    except Exception as e:
        print("Kurse fuer den Chart nicht verfuegbar: %s" % e)
        return [], {}


def main():
    if "@" not in UA:
        sys.exit("Fehler: SEC_USER_AGENT fehlt oder enthaelt keine Kontaktadresse (siehe Kopf der Datei).")

    from fetch_details import SECTORS
    stocks = {}
    for cfg in SECTORS.values():
        for t, name in cfg["stocks"]:
            stocks[t] = name

    state = load_json("insiders_state.json", {"tickers": {}})
    cutoff = (datetime.date.today() - datetime.timedelta(days=LOOKBACK_DAYS)).isoformat()
    deadline = time.time() + float(os.environ.get("INSIDER_BUDGET_MIN", "30")) * 60

    ciks_raw = http_get("https://www.sec.gov/files/company_tickers.json")
    if ciks_raw is None:
        sys.exit("Fehler: SEC-Tickerliste nicht abrufbar.")
    cik_map = {v["ticker"].upper(): int(v["cik_str"]) for v in json.loads(ciks_raw).values()}

    # unvollstaendige zuerst, damit Rueckstaende abgebaut werden
    order = sorted(stocks, key=lambda t: state["tickers"].get(t, {}).get("complete", False))
    done, open_, missing = 0, 0, []
    for t in order:
        cik = cik_map.get(t.upper())
        if cik is None:
            missing.append(t)
            continue
        entry = state["tickers"].setdefault(t, {"seen": {}, "tx": [], "complete": False})
        entry["cik"] = cik
        try:
            entry["complete"] = process_ticker(cik, entry, http_get, cutoff, deadline)
        except Exception as e:
            print("%s: Fehler %s" % (t, e))
            entry["complete"] = False
        done += 1 if entry["complete"] else 0
        open_ += 0 if entry["complete"] else 1
        print("%s: %d Transaktionen, %s" % (t, len(entry["tx"]), "komplett" if entry["complete"] else "offen"))

    pxdates, px = fetch_prices([t for t in stocks if t in state["tickers"]])
    out = {
        "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lookback_days": LOOKBACK_DAYS,
        "min_sell_value": MIN_SELL_VALUE,
        "pxdates": pxdates,
        "tickers": {t: {"name": stocks[t], "complete": e.get("complete", False), "tx": e["tx"], "px": px.get(t)}
                    for t, e in state["tickers"].items() if t in stocks},
    }
    with open("insiders.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    with open("insiders_state.json", "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    print("Fertig: %d komplett, %d offen, ohne SEC-Kennung: %s" % (done, open_, ", ".join(missing) or "keine"))


if __name__ == "__main__":
    main()
