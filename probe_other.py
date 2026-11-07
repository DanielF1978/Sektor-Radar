"""Testet, ob Anteilszahlen von iShares (BlackRock) und VanEck aus GitHub Actions abrufbar sind. Nur Diagnose."""
import re
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
ISHARES = [  # (Ticker, Produktnummer, Namensteil der Adresse)
    ("IBB", 239699, "ishares-nasdaq-biotechnology-etf"),
    ("IHI", 239516, "ishares-us-medical-devices-etf"),
    ("ITA", 239502, "ishares-us-aer-def-etf"),
]
VANECK = [
    ("SMH", "https://www.vaneck.com/us/en/investments/semiconductor-etf-smh/overview/"),
    ("GDX", "https://www.vaneck.com/us/en/investments/gold-miners-etf-gdx/overview/"),
    ("OIH", "https://www.vaneck.com/us/en/investments/oil-services-etf-oih/overview/"),
]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.status, r.headers.get("Content-Type"), r.read()


print("##### iShares")
for t, pid, slug in ISHARES:
    for url in (
        "https://www.ishares.com/us/products/%d/%s/1467271812596.ajax?fileType=csv&fileName=%s_holdings&dataType=fund" % (pid, slug, t),
        "https://www.ishares.com/us/products/%d/%s" % (pid, slug),
    ):
        print("\n== %s" % url)
        try:
            status, ctype, data = get(url)
            text = data.decode("utf-8", errors="replace")
            print("  HTTP %s, %s, %d Bytes" % (status, ctype, len(data)))
            lines = [l for l in text.splitlines() if l.strip()]
            for l in lines[:10]:
                print("   ", l[:160])
            for m in re.finditer(r"[^\n]{0,80}[Ss]hares [Oo]utstanding[^\n]{0,80}", text):
                print("  Treffer:", m.group(0)[:200]); break
        except Exception as e:
            print("  Fehler: %s" % e)

print("\n##### VanEck")
for t, url in VANECK:
    print("\n== %s" % url)
    try:
        status, ctype, data = get(url)
        text = data.decode("utf-8", errors="replace")
        print("  HTTP %s, %s, %d Bytes" % (status, ctype, len(data)))
        hits = 0
        for m in re.finditer(r"[^<>\n]{0,100}[Ss]hares [Oo]utstanding[^\n]{0,200}", text):
            print("  Treffer:", re.sub(r"\s+", " ", m.group(0))[:300]); hits += 1
            if hits >= 3:
                break
        if not hits:
            print("  kein Treffer fuer 'Shares Outstanding'")
    except Exception as e:
        print("  Fehler: %s" % e)
