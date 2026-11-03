"""Prueft nach jedem Kursabruf, ob ein Sektor den RRG-Quadranten gewechselt hat,
und schickt bei Wechseln eine Push-Nachricht ueber ntfy.

Taeglich:     jeden Lauf (SMA 30, Momentum-Abstand 10 Tage)
Woechentlich: nur wenn der letzte Handelstag ein Freitag ist (SMA 10, Abstand 4 Wochen)

Umgebungsvariablen:
  NTFY_TOPIC   Name des ntfy-Themas (als GitHub-Secret hinterlegen)
  DRY_RUN=1    Nachrichten nur ausgeben, nicht senden (State wird trotzdem gespeichert)
  WEEKLY_ANY_DAY=1  woechentliche Pruefung an jedem Tag (zum Testen)
"""
import datetime
import json
import os
import sys
import urllib.request

SECTORS = {
    "XLK": "Technologie", "XLF": "Finanzwesen", "XLY": "Zyklischer Konsum", "XLC": "Kommunikation",
    "XLI": "Industrie", "XLB": "Materialien", "XLE": "Energie", "XLV": "Gesundheitswesen",
    "XLP": "Basiskonsumgüter", "XLU": "Versorger", "XLRE": "Immobilien",
}
BENCH = "SPY"
CFG = {"d": {"sma": 30, "lag": 10}, "w": {"sma": 10, "lag": 4}}
LABEL = {"d": "täglich", "w": "wöchentlich"}
MARGIN = 0.3  # Abstand zur 100er-Linie, ab dem ein Seitenwechsel zaehlt
SITE = "https://danielf1978.github.io/Sektor-Radar/"

HINT = {
    "Leading": "Geld kommt rein",
    "Weakening": "Dynamik lässt nach",
    "Lagging": "Geld geht raus",
    "Improving": "erste Erholung",
}


def week_indices(dates):
    last, order = {}, []
    for i, ds in enumerate(dates):
        d = datetime.date.fromisoformat(ds)
        mon = (d - datetime.timedelta(days=d.weekday())).isoformat()
        if mon not in last:
            order.append(mon)
        last[mon] = i
    return [last[k] for k in order]


def latest_point(sec, bench, sma, lag):
    """Letzter (Ratio, Momentum)-Punkt, gleiche Formeln wie index.html."""
    rs = [s / b for s, b in zip(sec, bench)]
    n = len(rs)
    if n < sma + lag:
        return None

    def ratio_at(i):
        return 100 * rs[i] / (sum(rs[i - sma + 1:i + 1]) / sma)

    r_now, r_prev = ratio_at(n - 1), ratio_at(n - 1 - lag)
    return r_now, 100 * r_now / r_prev


def quadrant(right, up):
    if right and up:
        return "Leading"
    if right and not up:
        return "Weakening"
    if not right and not up:
        return "Lagging"
    return "Improving"


def side(value, prev_side):
    """Seite der 100er-Linie mit Puffer: innerhalb des Puffers bleibt die alte Seite."""
    if value >= 100 + MARGIN:
        return True
    if value <= 100 - MARGIN:
        return False
    return prev_side if prev_side is not None else value >= 100


def evaluate(data, mode, prev):
    cfg = CFG[mode]
    idx = week_indices(data["dates"]) if mode == "w" else list(range(len(data["dates"])))
    bench = [data["series"][BENCH][i] for i in idx]
    out = {}
    for t in SECTORS:
        sec = [data["series"][t][i] for i in idx]
        p = latest_point(sec, bench, cfg["sma"], cfg["lag"])
        if p is None:
            continue
        old = prev.get(t)
        px = old in ("Leading", "Weakening") if old else None
        py = old in ("Leading", "Improving") if old else None
        out[t] = quadrant(side(p[0], px), side(p[1], py))
    return out


def send(topic, title, body, priority, tags):
    if os.environ.get("DRY_RUN") == "1":
        print("[DRY_RUN] %s | prio %s | %s\n%s\n" % (title, priority, tags, body))
        return
    req = urllib.request.Request(
        "https://ntfy.sh/" + topic,
        data=body.encode("utf-8"),
        headers={"Title": title, "Priority": str(priority), "Tags": tags, "Click": SITE},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


def main():
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    dry = os.environ.get("DRY_RUN") == "1"
    if not topic and not dry:
        print("Hinweis: NTFY_TOPIC ist nicht gesetzt, keine Benachrichtigung, State bleibt unveraendert.")
        return 0

    with open("data.json", encoding="utf-8") as f:
        data = json.load(f)
    last_date = data["dates"][-1]
    friday = datetime.date.fromisoformat(last_date).weekday() == 4
    try:
        with open("state.json", encoding="utf-8") as f:
            state = json.load(f)
    except FileNotFoundError:
        state = {}

    first_run = not state
    modes = ["d"] + (["w"] if friday or os.environ.get("WEEKLY_ANY_DAY") == "1" else [])
    errors = 0

    for mode in modes:
        prev = state.get(mode, {})
        cur = evaluate(data, mode, prev)
        changes = [(t, prev[t], cur[t]) for t in cur if t in prev and prev[t] != cur[t]]
        if changes:
            lines = ["%s %s: %s → %s (%s)" % (t, SECTORS[t], a, b, HINT[b]) for t, a, b in changes]
            important = any(b in ("Leading", "Lagging") for _, _, b in changes)
            title = "Sektor-Radar %s: %d Wechsel" % ("taeglich" if mode == "d" else "woechentlich", len(changes))
            body = "Stand " + last_date + " (" + LABEL[mode] + ")\n" + "\n".join(lines)
            try:
                send(topic, title, body, 4 if important else 3, "chart_with_upwards_trend")
            except Exception as e:  # State dann nicht aktualisieren, naechster Lauf versucht es erneut
                print("Senden fehlgeschlagen (%s): %s" % (mode, e))
                errors += 1
                continue
        state[mode] = cur
        state[mode + "_date"] = last_date
        print("%s: %d Sektoren geprueft, %d Wechsel" % (mode, len(cur), len(changes)))

    if first_run:
        try:
            send(topic, "Sektor-Radar eingerichtet",
                 "Benachrichtigungen sind aktiv. Du bekommst eine Meldung, wenn ein Sektor den RRG-Quadranten wechselt.",
                 3, "white_check_mark")
        except Exception as e:
            print("Startnachricht fehlgeschlagen: %s" % e)

    with open("state.json", "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
