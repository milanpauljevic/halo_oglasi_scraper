"""Prati nove oglase za izdavanje stanova na HaloOglasi i šalje ih na Telegram."""

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests
import yaml
from bs4 import BeautifulSoup

from notifier import TelegramNotifier

BASE_URL = "https://www.halooglasi.com"
ROOT = Path(__file__).resolve().parent
SEEN_FILE = ROOT / "seen.json"
SEEN_RETENTION_DAYS = 120

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept-Language": "sr-RS,sr;q=0.9,en;q=0.8",
}

# HaloOglasi u URL-u koristi redni broj opcije, a ne sam broj soba.
ROOMS_ORDER = {0.5: 1, 1.0: 2, 1.5: 3, 2.0: 4, 2.5: 5, 3.0: 7, 3.5: 8, 4.0: 9, 4.5: 10, 5.0: 11}
EUR_UNIT = 4


def normalize(text: str) -> str:
    text = text.lower().replace("đ", "dj")
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def build_search_url(cfg: dict, page: int) -> str:
    path = f"/nekretnine/izdavanje-stanova/{cfg['grad']}"
    if cfg.get("lokacija"):
        path += f"-{cfg['lokacija']}"
    params = {}
    if cfg.get("cena_min") is not None:
        params["cena_d_from"] = cfg["cena_min"]
    if cfg.get("cena_max") is not None:
        params["cena_d_to"] = cfg["cena_max"]
    if params:
        params["cena_d_unit"] = EUR_UNIT
    for key, param in (("sobe_min", "broj_soba_order_i_from"), ("sobe_max", "broj_soba_order_i_to")):
        if cfg.get(key) is not None:
            value = float(cfg[key])
            if value not in ROOMS_ORDER:
                raise ValueError(f"{key}={cfg[key]} nije podržano; dozvoljeno: {sorted(ROOMS_ORDER)}")
            params[param] = ROOMS_ORDER[value]
    if page > 1:
        params["page"] = page
    return BASE_URL + path + ("?" + urlencode(params) if params else "")


def parse_number(text: str):
    m = re.search(r"\d+(?:[.,]\d+)?", text or "")
    return float(m.group().replace(",", ".")) if m else None


def parse_listings(page_html: str) -> list[dict]:
    soup = BeautifulSoup(page_html, "html.parser")
    listings = []
    for item in soup.select("div.product-item[data-id]"):
        title_a = item.select_one("h3.product-title a")
        if not title_a:
            continue
        price_el = item.select_one(".central-feature span[data-value]")
        price = None
        if price_el:
            digits = re.sub(r"\D", "", price_el["data-value"])
            price = int(digits) if digits else None

        features = {}
        for wrapper in item.select("ul.product-features .value-wrapper"):
            legend = wrapper.select_one(".legend")
            if not legend:
                continue
            name = legend.get_text(strip=True)
            legend.extract()
            for sup in wrapper.select("sup"):
                sup.extract()
            features[name] = wrapper.get_text(" ", strip=True).replace(" m", "").strip()

        img = item.select_one("figure img")
        advertiser = item.select_one(".basic-info [data-field-name='oglasivac_nekretnine_s']")
        description = item.select_one(".product-description")
        date = item.select_one(".publish-date")
        rooms_text = features.get("Broj soba", "")

        listings.append({
            "id": item["data-id"],
            "title": title_a.get_text(strip=True),
            "url": BASE_URL + title_a["href"].split("?")[0],
            "price": price,
            "area": parse_number(features.get("Kvadratura", "")),
            "rooms": parse_number(rooms_text),
            "rooms_text": rooms_text,
            "floor": features.get("Spratnost", ""),
            "location": [li.get_text(strip=True) for li in item.select("ul.subtitle-places li")],
            "description": description.get_text(" ", strip=True) if description else "",
            "advertiser": advertiser.get_text(strip=True) if advertiser else "",
            "published": date.get_text(strip=True) if date else "",
            "image": img["src"] if img and "no-image" not in img.get("src", "") else None,
        })
    return listings


def total_pages(page_html: str) -> int:
    m = re.search(r'"TotalPages"\s*:\s*(\d+)', page_html)
    return int(m.group(1)) if m else 1


def total_count(page_html: str):
    m = re.search(r'"TotalCount"\s*:\s*(\d+)', page_html)
    return int(m.group(1)) if m else None


def fetch(session: requests.Session, url: str) -> str:
    last_error = None
    for attempt in range(3):
        try:
            resp = session.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                return resp.text
            last_error = f"HTTP {resp.status_code}"
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Neuspešno preuzimanje {url}: {last_error}")


def scrape(cfg: dict) -> list[dict]:
    session = requests.Session()
    delay = cfg.get("pauza_sekunde", 2)
    max_pages = cfg.get("max_strana", 30)
    results: dict[str, dict] = {}
    page, pages = 1, 1
    while page <= min(pages, max_pages):
        url = build_search_url(cfg, page)
        page_html = fetch(session, url)
        listings = parse_listings(page_html)
        if page == 1:
            pages = total_pages(page_html)
            count = total_count(page_html)
            print(f"Pretraga: {url}\nUkupno oglasa na sajtu: {count}, strana: {pages}")
            if count and not listings:
                raise RuntimeError("Sajt prijavljuje oglase, ali nijedan nije pročitan — verovatno je promenjen HTML.")
        if not listings:
            break
        for l in listings:
            results.setdefault(l["id"], l)
        page += 1
        if page <= min(pages, max_pages):
            time.sleep(delay)
    return list(results.values())


def matches(l: dict, cfg: dict) -> bool:
    if cfg.get("cena_max") is not None and l["price"] is not None and l["price"] > cfg["cena_max"]:
        return False
    if cfg.get("cena_min") is not None and l["price"] is not None and l["price"] < cfg["cena_min"]:
        return False
    if cfg.get("sobe_min") is not None and l["rooms"] is not None and l["rooms"] < float(cfg["sobe_min"]):
        return False
    if cfg.get("sobe_max") is not None and l["rooms"] is not None and l["rooms"] > float(cfg["sobe_max"]):
        return False
    location = normalize(" ".join(l["location"]))
    if any(re.search(rf"\b{re.escape(normalize(x))}\b", location) for x in cfg.get("iskljuci_lokacije") or []):
        return False
    text = normalize(l["title"] + " " + l["description"])
    if any(normalize(x) in text for x in cfg.get("iskljuci_reci") or []):
        return False
    return True


def load_seen() -> dict:
    if SEEN_FILE.exists():
        return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    return {}


def save_seen(seen: dict) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=SEEN_RETENTION_DAYS)).isoformat()
    seen = {k: v for k, v in seen.items() if v >= cutoff}
    SEEN_FILE.write_text(json.dumps(dict(sorted(seen.items())), indent=0) + "\n", encoding="utf-8")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="samo ispiši nove oglase, bez Telegrama i bez čuvanja stanja")
    parser.add_argument("--test-telegram", action="store_true", help="pošalji probnu poruku na Telegram i izađi")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))

    notifier = None
    if not args.dry_run:
        token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            print("Greška: postavi TELEGRAM_BOT_TOKEN i TELEGRAM_CHAT_ID (ili koristi --dry-run).")
            return 2
        notifier = TelegramNotifier(token, chat_id)
        if args.test_telegram:
            notifier.send_text("✅ HaloOglasi skrejper je povezan sa Telegramom.")
            print("Probna poruka poslata.")
            return 0

    listings = [l for l in scrape(cfg) if matches(l, cfg)]
    seen = load_seen()
    first_run = not SEEN_FILE.exists()
    new = [l for l in listings if l["id"] not in seen]
    print(f"Odgovara filterima: {len(listings)}, novih: {len(new)}")

    if args.dry_run:
        for l in new:
            print(f"- {l['price']} € | {l['rooms_text']} soba | {l['area']} m² | {', '.join(l['location'])}\n  {l['title']}\n  {l['url']}")
        return 0

    now = datetime.now(timezone.utc).isoformat()
    refresh_before = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    for l in listings:
        # Aktivni oglasi se povremeno osvežavaju da ne isteknu iz seen.json (a da se fajl ne menja svaki put).
        if l["id"] in seen and seen[l["id"]] < refresh_before:
            seen[l["id"]] = now

    if first_run:
        for l in new:
            seen[l["id"]] = now
        save_seen(seen)
        print(f"Prvo pokretanje: zapamćeno {len(new)} postojećih oglasa, poruke nisu poslate.")
        notifier.send_text(f"✅ Praćenje pokrenuto. Trenutno {len(new)} oglasa odgovara filterima; javljam samo nove.")
        return 0

    errors = 0
    for l in reversed(new):  # najstariji prvo, da najnoviji bude na dnu chata
        try:
            notifier.send_listing(l)
            seen[l["id"]] = now
        except Exception as exc:  # pokušaće ponovo sledeći put
            errors += 1
            print(f"Slanje oglasa {l['id']} nije uspelo: {exc}")
        time.sleep(1)
    save_seen(seen)
    print(f"Poslato: {len(new) - errors}, neuspešno: {errors}")
    return 1 if errors and errors == len(new) else 0


if __name__ == "__main__":
    sys.exit(main())
