"""Testet, ob die taeglichen Fondsdaten (Nettoinventarwert, Anteile, Fondsvermoegen) von State Street (SPDR)
aus GitHub Actions abrufbar sind. Gibt nur Diagnose aus, schreibt nichts."""
import io
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
BASES = [
    "https://www.ssga.com/library-content/products/fund-data/etfs/us/navhist-us-en-%s.xlsx",
    "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/navhist-us-en-%s.xlsx",
]
TICKERS = ["xlk", "xle", "xbi"]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.status, r.headers.get("Content-Type"), r.read()


def show(data):
    try:
        import openpyxl
    except ImportError:
        print("  openpyxl fehlt")
        return
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as e:
        print("  keine gueltige xlsx-Datei: %s | Anfang: %r" % (e, data[:200]))
        return
    for ws in wb.worksheets:
        print("  Blatt: %s" % ws.title)
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i < 12:
                print("   ", [c for c in row if c is not None])
            else:
                break


for t in TICKERS:
    for b in BASES:
        url = b % t
        print("\n== %s" % url)
        try:
            status, ctype, data = get(url)
            print("  HTTP %s, %s, %d Bytes" % (status, ctype, len(data)))
            show(data)
            break
        except Exception as e:
            print("  Fehler: %s" % e)
