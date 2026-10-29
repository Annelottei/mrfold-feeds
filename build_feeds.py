#!/usr/bin/env python3
"""Bouwt de Franse en Duitse Meta-catalogusfeeds voor Mr Fold.

Gebruikt alleen openbare winkelgegevens (/<markt>/products.json), geen exports of tokens.
Draaien: python3 build_feeds.py <uitvoermap>
id = Shopify-variant-ID, zodat de pixel de aankopen aan dezelfde items koppelt.
Bij een fout of een verdacht klein resultaat stopt het script zonder bestanden te overschrijven.
"""
import csv, html, json, re, sys, time, urllib.request
from pathlib import Path

BASE = "https://mr-fold.com"
MARKETS = {
    "fr": {"path": "fr-fr"},
    "de": {"path": "de-de"},
}
# nooit in de carrousel (NL-handles); concepten en niet-gepubliceerde producten staan niet in products.json
EXCLUDE = {"nieuwe-product", "test", "divers", "cadeaubon-50", "meerijdplankje"}
EXCLUDE_PREFIX = ("w-series", "dakje-n-series")
MIN_ROWS = 100

# Handmatige correcties op de vertalingen in Shopify (sleutel: taal, NL-handle).
FIX = {
    ("de", "parapluhouder"): {"description": (
        "✓ Halte deine Hände frei, um den Wagen zu lenken.\n"
        "✓ Auch die Kleinen, die sich an der Schubstange festhalten, bleiben trocken.\n"
        "Lieferzeit 7 Tage, der Regenschirm ist nicht im Lieferumfang enthalten.")},
    ("de", "acc-wheelcover"): {"title": "Radüberzüge (Set)", "description": (
        "Halte dein Auto und dein Zuhause sauber – mit den praktischen Radüberzügen von Mr Fold. "
        "Die Überzüge schützen vor Schmutz und Schlamm und lassen sich einfach an den Rädern befestigen. "
        "Ideal für unterwegs, leicht zu verstauen und perfekt passend für deinen Wagen.")},
    ("de", "wiegje"): {"title": "Maxi-Cosi-Halterung / Babywiege", "description": (
        "✓ Nur für den 4-Sitzer und 6-Sitzer Wagen geeignet.\n"
        "✓ Weiche Polsterung und atmungsaktives Material für mehr Komfort.\n"
        "✓ Sichere Befestigung: bleibt fest an seinem Platz.\n"
        "✓ Einfach zu montieren und abzunehmen.\n"
        "✓ Kompakt faltbar für einfachen Transport.")},
    ("de", "kinderschaal"): {"title": "Babysitz für Kinderwagen"},
    ("de", "p-series-luxe-6-zits-kinderkar"): {"description": (
        "Der Kinderwagen wird standardmäßig mit dem Sonnendach, den Sitzen und den Aufbewahrungstaschen "
        "geliefert, wie auf den Produktbildern gezeigt.\n✓ Platz für sechs bis acht Kinder.")},
}
REPLACE = [
    ("de", "kinderschaal", "(0–18 Monate)", "(0–9 Monate)"),
    ("de", "p2-luxe-2-zits-kinderkar", "Aufbewastungeln", "Aufbewahrungstaschen"),
    ("de", "p4-luxe-4-zits-kinderkar", "Platz für bis zu vier Kinder.", "Platz für vier bis sechs Kinder."),
    ("fr", "p2-luxe-2-zits-kinderkar", "Place pour deux enfants.", "Place pour deux à trois enfants."),
    ("fr", "p4-luxe-4-zits-kinderkar", "jusqu’à quatre enfants", "de quatre à six enfants"),
    ("fr", "p-series-luxe-6-zits-kinderkar", "jusqu’à six enfants", "de six à huit enfants"),
    ("fr", "wiegje", "poussettess", "poussettes"),
]
DROP_LINES = [
    ("de", "boodschappenmandje", "❗"),
    ("de", "boodschappenmandje", "und nicht auf die W-Serie"),
    ("de", "snackbakje", "❗"),
]
OPT_FALLBACK = {
    "fr": {"Blauw": "Bleu", "Wit": "Blanc", "Standaard": "Standard"},
    "de": {"Blauw": "Blau", "Wit": "Weiß", "Standaard": "Standard"},
}
ROOF = {"fr": "toit", "de": "Dach"}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (feed-builder)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    time.sleep(0.5)
    return data


def products(market):
    out, page = [], 1
    while True:
        batch = get(f"{BASE}/{market}/products.json?limit=250&page={page}")["products"]
        out += batch
        if len(batch) < 250:
            return {p["id"]: p for p in out}
        page += 1


def clean(text):
    text = re.sub(r"<(br|/p|/li|/h\d)\s*/?>", "\n", text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text).strip()
    return text[:5000]


def apply_fixes(loc, h, title, desc, report):
    fx = FIX.get((loc, h), {})
    title = fx.get("title", title)
    desc = fx.get("description", desc)
    for l, hh, old, new in REPLACE:
        if (l, hh) == (loc, h):
            if old in desc:
                desc = desc.replace(old, new)
            else:
                report.append(f"{loc}: {h} -> correctie '{old}' niet toegepast (tekst niet gevonden)")
    for l, hh, start in DROP_LINES:
        if (l, hh) == (loc, h):
            desc = "\n".join(x for x in desc.split("\n") if not x.startswith(start))
    return title, desc, bool(fx)


def main(outdir):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    nl = {i: p for i, p in products("nl-nl").items()
          if p["handle"] not in EXCLUDE and not p["handle"].startswith(EXCLUDE_PREFIX)}
    report, results = [], {}
    for loc, m in MARKETS.items():
        loc_products = products(m["path"])
        optmap = dict(OPT_FALLBACK[loc])
        rows = []
        for pid, n in nl.items():
            p = loc_products.get(pid)
            if not p:
                report.append(f"{loc}: {n['handle']} -> niet gevonden in {m['path']}, overgeslagen")
                continue
            nvars = {v["id"]: v for v in n["variants"]}
            for v in p["variants"]:
                nv = nvars.get(v["id"])
                if nv:
                    for k in ("option1", "option2", "option3"):
                        if nv.get(k) and v.get(k) and nv[k] != v[k]:
                            optmap.setdefault(nv[k], v[k])
            title, desc, fixed = apply_fixes(loc, n["handle"], p["title"].strip(), clean(p.get("body_html")), report)
            if not fixed and title == n["title"].strip():
                report.append(f"{loc}: {n['handle']} -> titel niet vertaald, overgeslagen")
                continue
            if not fixed and desc == clean(n.get("body_html")):
                report.append(f"{loc}: {n['handle']} -> beschrijving niet vertaald, overgeslagen")
                continue
            tr = lambda x: optmap.get(x, x)
            names = [o["name"].lower() for o in n.get("options", [])]
            for v in p["variants"]:
                nv = nvars.get(v["id"], v)
                o = [x for x in (nv.get("option1"), nv.get("option2"), nv.get("option3"))
                     if x and x != "Default Title"]
                refurb = "Retourdeal" in o
                parts = [tr(x) for x in o if x not in ("Nieuw", "Retourdeal")]
                color = parts[0] if parts else ""
                if len(parts) > 1 and len(names) > 1 and names[1].startswith("dak"):
                    sep = " : " if loc == "fr" else ": "
                    color = f"{parts[0]} ({ROOF[loc]}{sep}{parts[1]})"
                elif len(parts) > 1:
                    color = " / ".join(parts)
                if refurb:
                    color += f" – {tr('Retourdeal')}"
                img = (v.get("featured_image") or {}).get("src") or (p.get("images") or [{}])[0].get("src", "")
                price = float(v["price"])
                compare = float(v.get("compare_at_price") or 0)
                rows.append([
                    v["id"], title, desc,
                    "in stock" if v.get("available") else "out of stock",
                    "refurbished" if refurb else "new",
                    f"{max(price, compare):.2f} EUR",
                    f"{price:.2f} EUR" if compare > price else "",
                    f"{BASE}/{m['path']}/products/{p['handle']}?variant={v['id']}",
                    img, "Mr Fold", p["id"], color,
                ])
        results[loc] = rows
    for loc, rows in results.items():
        if len(rows) < MIN_ROWS:
            print(f"FOUT: {loc} heeft maar {len(rows)} regels (minimaal {MIN_ROWS}); niets overschreven", file=sys.stderr)
            sys.exit(1)
    for loc, rows in results.items():
        with open(out / f"catalogus_{loc}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "title", "description", "availability", "condition", "price", "sale_price",
                        "link", "image_link", "brand", "item_group_id", "color"])
            w.writerows(rows)
        print(f"catalogus_{loc}.csv: {len(rows)} regels")
    (out / "rapport.txt").write_text("\n".join(report) or "geen opmerkingen", encoding="utf-8")
    for r in report:
        print(r)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
