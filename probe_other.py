"""Testet, ob die Anteilszahl von iShares und VanEck aus GitHub Actions auslesbar ist. Nur Diagnose, schreibt nichts."""
import html
import http.cookiejar
import re
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
PAGES = [
    ("IBB", "https://www.ishares.com/us/products/239699/ishares-nasdaq-biotechnology-etf"),
    ("IHI", "https://www.ishares.com/us/products/239516/ishares-us-medical-devices-etf"),
    ("SMH", "https://www.vaneck.com/us/en/investments/semiconductor-etf-smh/overview/"),
    ("GDX", "https://www.vaneck.com/us/en/investments/gold-miners-etf-gdx/overview/"),
]


def get(url):
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    op.addheaders = [("User-Agent", UA), ("Accept", "text/html,application/xhtml+xml,*/*"), ("Accept-Language", "en-US,en;q=0.9")]
    with op.open(url, timeout=40) as r:
        return r.status, r.read().decode("utf-8", errors="replace")


def text_of(s):
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s))


for t, url in PAGES:
    print("\n== %s %s" % (t, url))
    try:
        status, page = get(url)
    except Exception as e:
        print("  Fehler: %s" % str(e)[:200])
        continue
    print("  HTTP %s, %d Zeichen" % (status, len(page)))
    txt = text_of(page)
    found = 0
    for m in re.finditer(r"(Shares Outstanding|Shares Out\.?|Net Assets of Fund|NAV as of)", txt):
        seg = txt[m.start():m.start() + 160]
        if re.search(r"\d{1,3}(,\d{3})+", seg) or "as of" in seg.lower():
            print("  Text:", seg)
            found += 1
            if found >= 6:
                break
    for m in re.finditer(r"(?i)shares\s*outstanding[^<]{0,40}<[^>]*>[^<]{0,40}<[^>]*>[^<]{0,60}", page):
        print("  HTML:", re.sub(r"\s+", " ", m.group(0))[:260])
        break
    if not found:
        print("  keine Zahl bei 'Shares Outstanding' gefunden")
