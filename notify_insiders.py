"""Meldet neue Insider-Cluster-Kaeufe per ntfy.

Cluster = mindestens 3 verschiedene Insider, die in den letzten 90 Tagen am offenen Markt gekauft haben.
Gemeldet wird, wenn ein Wert neu zum Cluster wird oder weitere Kaeufer dazukommen. Faellt ein Wert unter
3 Kaeufer, wird er zurueckgesetzt. Der erste Lauf meldet nur eine Uebersicht der bestehenden Cluster.

Umgebungsvariablen: NTFY_TOPIC (Pflicht zum Senden), DRY_RUN=1 (nur ausgeben).
"""
import datetime
import json
import os
import sys
import urllib.request

SITE = "https://danielf1978.github.io/Sektor-Radar/"
STATE = "insider_alerts.json"
DAYS = 90
MIN_BUYERS = 3


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def usd(v):
    return "%.1f Mio. $" % (v / 1e6) if v >= 1e6 else "%d Tsd. $" % round(v / 1e3)


def clusters(data):
    cut = (datetime.date.today() - datetime.timedelta(days=DAYS)).isoformat()
    out = {}
    for t, e in data.get("tickers", {}).items():
        buyers, total, last = set(), 0.0, ""
        for x in e.get("tx", []):
            if x["a"] == "B" and x["d"] >= cut:
                buyers.add(x["n"])
                total += x["v"]
                last = max(last, x["d"])
        if len(buyers) >= MIN_BUYERS:
            out[t] = {"name": e.get("name", t), "nb": len(buyers), "sum": total, "last": last}
    return out


def send(topic, title, body, priority, tags):
    if os.environ.get("DRY_RUN") == "1":
        print("[DRY_RUN] %s | prio %s | %s\n%s\n" % (title, priority, tags, body))
        return
    req = urllib.request.Request("https://ntfy.sh/" + topic, data=body.encode("utf-8"),
                                 headers={"Title": title.encode("utf-8"), "Priority": str(priority),
                                          "Tags": tags, "Click": SITE}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


def main():
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    dry = os.environ.get("DRY_RUN") == "1"
    if not topic and not dry:
        print("Hinweis: NTFY_TOPIC fehlt, keine Meldung, Stand bleibt unveraendert.")
        return
    data = load("insiders.json", None)
    if not data:
        print("Keine insiders.json vorhanden.")
        return
    cur = clusters(data)
    state = load(STATE, None)
    first = state is None
    state = state or {}

    if first:
        if cur:
            lines = ["%s (%s): %d Käufer, %s" % (v["name"], t, v["nb"], usd(v["sum"]))
                     for t, v in sorted(cur.items(), key=lambda kv: -kv[1]["sum"])[:10]]
            send(topic, "Insider-Radar eingerichtet",
                 "Ab jetzt melde ich neue Cluster-Käufe. Aktuell bestehen:\n" + "\n".join(lines), 3, "eyes")
        else:
            send(topic, "Insider-Radar eingerichtet", "Aktuell gibt es keine Cluster-Käufe.", 3, "eyes")
        new_state = {t: {"nb": v["nb"]} for t, v in cur.items()}
    else:
        new_state = {}
        for t, v in cur.items():
            old = state.get(t, {}).get("nb", 0)
            new_state[t] = {"nb": max(old, v["nb"])}
            if v["nb"] > old:
                head = "Neuer Cluster-Kauf" if old == 0 else "Weitere Insider kaufen"
                send(topic, "%s: %s (%s)" % (head, v["name"], t),
                     "%d verschiedene Insider kauften in 90 Tagen für zusammen %s (letzter Kauf %s)."
                     % (v["nb"], usd(v["sum"]), v["last"]), 4, "moneybag")
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(new_state, f, sort_keys=True, indent=0)
    print("Cluster aktuell: %d, gemeldet seit letztem Stand: %s" % (
        len(cur), "Uebersicht" if first else sum(1 for t in cur if cur[t]["nb"] > state.get(t, {}).get("nb", 0))))


if __name__ == "__main__":
    main()
