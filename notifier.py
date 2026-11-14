import html
import re
import time

import requests

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        # Token nikad ne sadrži razmake; uklanjamo ih ako su se ubacili pri kopiranju sa telefona.
        self.token = re.sub(r"\s", "", token)
        self.chat_id = chat_id.strip()

    def check(self) -> None:
        """Proverava token i chat id pre skrejpovanja, sa jasnom porukom šta ne valja."""
        resp = requests.get(API.format(token=self.token, method="getMe"), timeout=30)
        if resp.status_code == 401 or resp.status_code == 404:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN nije ispravan (Telegram: Unauthorized). Kopiraj ceo token od @BotFather-a, "
                "u obliku 123456789:AAH..., bez razmaka, navodnika i bez reči 'bot' ispred."
            )
        resp = requests.post(API.format(token=self.token, method="getChat"), data={"chat_id": self.chat_id}, timeout=30)
        if not resp.json().get("ok"):
            raise RuntimeError(
                f"TELEGRAM_CHAT_ID nije ispravan ({resp.json().get('description')}). Proveri broj od @userinfobot "
                "i da si svom botu poslao /start."
            )

    def _call(self, method: str, payload: dict) -> dict:
        for attempt in range(3):
            resp = requests.post(API.format(token=self.token, method=method), data=payload, timeout=30)
            if resp.status_code == 429:
                retry = resp.json().get("parameters", {}).get("retry_after", 5)
                time.sleep(retry + 1)
                continue
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(f"Telegram {method} greška: {data.get('description')}")
            return data
        raise RuntimeError(f"Telegram {method}: previše zahteva (429)")

    def send_text(self, text: str) -> None:
        self._call("sendMessage", {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "false",
        })

    def send_listing(self, listing: dict) -> None:
        caption = format_listing(listing)
        if listing.get("image"):
            try:
                self._call("sendPhoto", {
                    "chat_id": self.chat_id,
                    "photo": listing["image"],
                    "caption": caption,
                    "parse_mode": "HTML",
                })
                return
            except RuntimeError:
                pass  # npr. slika nedostupna — pošalji bar tekst
        self.send_text(caption)


def format_listing(l: dict) -> str:
    e = html.escape
    lines = [f"🏠 <b>{e(l['title'])}</b>"]
    price = f"{l['price']:,} €".replace(",", ".") if l.get("price") is not None else "cena na upit"
    details = [price]
    if l.get("area"):
        details.append(f"{l['area']:g} m²")
    if l.get("rooms_text"):
        details.append(f"{l['rooms_text']} soba")
    if l.get("floor"):
        details.append(f"sprat {l['floor']}")
    lines.append("💶 " + " · ".join(e(d) for d in details))
    if l.get("location"):
        lines.append("📍 " + e(", ".join(l["location"])))
    if l.get("advertiser"):
        lines.append("👤 " + e(l["advertiser"]))
    lines.append(f'🔗 <a href="{e(l["url"])}">Otvori oglas</a>')
    return "\n".join(lines)
