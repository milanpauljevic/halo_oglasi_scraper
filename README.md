# HaloOglasi skrejper

Na svakih ~15 minuta proverava nove oglase za izdavanje stanova na [HaloOglasi](https://www.halooglasi.com)
i za svaki nov oglas šalje Telegram poruku (slika, cena, m², sobe, lokacija, link).
Radi besplatno na GitHub Actions — i kad ti je računar ugašen.

Filteri su u [config.yaml](config.yaml): Novi Beograd, do 600 €, 2.0+ sobe, bez Ledina i Surčina.

## 1. Napravi Telegram bota (2 min)

1. U Telegramu otvori **@BotFather**, pošalji `/newbot`, izaberi ime.
2. Dobićeš **token** (npr. `123456:ABC-...`). Sačuvaj ga — to je lozinka bota, ne deli je.
3. Otvori svog novog bota i pošalji mu bilo koju poruku (npr. `zdravo`).
4. U browseru otvori `https://api.telegram.org/bot<TOKEN>/getUpdates` i nađi `"chat":{"id": 123456789`.
   Taj broj je tvoj **chat id**.

## 2. Postavi na GitHub

1. Napravi nov repo na GitHub-u. **Javni** repo ima neograničene besplatne Actions minute;
   za **privatni** (2000 min/mesec) u `.github/workflows/scrape.yml` promeni cron na `*/30 * * * *`.
2. Postavi kod (bez `.venv` — već je u `.gitignore`):
   ```powershell
   cd c:\HaloOglasiScraper
   git init -b main
   git add .
   git commit -m "HaloOglasi skrejper"
   git remote add origin https://github.com/<korisnik>/<repo>.git
   git push -u origin main
   ```
3. U repou: **Settings → Secrets and variables → Actions → New repository secret**, dodaj:
   - `TELEGRAM_BOT_TOKEN` — token od BotFather-a
   - `TELEGRAM_CHAT_ID` — tvoj chat id
   - `PROXY_URL` — adresa proxy-ja (vidi ispod)
4. **Actions** tab → *HaloOglasi skrejper* → **Run workflow** da ga odmah pokreneš.
   Prvo pokretanje samo zapamti postojeće oglase i pošalje poruku „Praćenje pokrenuto“.
   Posle toga stižu samo novi oglasi.

## Proxy (obavezan za GitHub)

HaloOglasi je iza Cloudflare zaštite koja blokira GitHub servere (i pravi Chrome), a pušta kućne IP adrese.
Zato na GitHub-u zahtevi idu preko **rezidencijalnog proxy-ja** (nečija kućna IP adresa).

1. Otvori nalog kod provajdera rezidencijalnih proxy-ja koji naplaćuje po GB (npr. DataImpulse, ~1 $/GB).
   Skripta troši oko 0,1–0,5 GB mesečno.
2. U njihovom panelu uzmi podatke za pristup: host, port, korisničko ime i lozinku. Izaberi **rotirajuće**
   IP adrese, po želji iz Srbije.
3. Dodaj GitHub secret `PROXY_URL` u obliku `http://korisnik:lozinka@host:port`.

Ako `PROXY_URL` nije postavljen, skripta ide direktno (to radi sa kućnog interneta).
Lokalni test proxy-ja: `$env:PROXY_URL="http://korisnik:lozinka@host:port"; .\.venv\Scripts\python.exe scraper.py --dry-run`

## Izmena filtera

Izmeni [config.yaml](config.yaml) (direktno na GitHub-u ili lokalno pa `git push`). Ako želiš da te
posle izmene obavesti i o već postojećim oglasima koji sada odgovaraju, obriši `seen.json` — prvo
sledeće pokretanje će ih tada samo zapamtiti, a ne poslati.

## Lokalno pokretanje

```powershell
cd c:\HaloOglasiScraper
.\.venv\Scripts\python.exe scraper.py --dry-run          # samo ispis, bez Telegrama i bez čuvanja
$env:TELEGRAM_BOT_TOKEN="..."; $env:TELEGRAM_CHAT_ID="..."
.\.venv\Scripts\python.exe scraper.py --test-telegram    # probna poruka
.\.venv\Scripts\python.exe scraper.py                    # pravo pokretanje
```

Novo okruženje: `python -m venv .venv` pa `.\.venv\Scripts\pip install -r requirements.txt`.

## Napomene

- GitHub cron nije precizan; kašnjenje od 5–15 min je normalno.
- HaloOglasi je iza Cloudflare zaštite. Ako i pored proxy-ja stigne Cloudflare provera, skripta pokušava
  sa drugom IP adresom, a zatim pokreće pravi Chrome (SeleniumBase UC režim) preko istog proxy-ja.
  Lokalno možeš da testiraš Chrome režim sa `$env:FORCE_BROWSER="1"`.
- Kad ti skrejper više ne treba: **Actions → HaloOglasi skrejper → „…“ → Disable workflow**.
- Ako dobiješ grešku „nijedan oglas nije pročitan“, HaloOglasi je promenio izgled stranice i parser
  u `scraper.py` treba ažurirati.
- `seen.json` čuva ID-jeve viđenih oglasa (stariji od 120 dana se brišu).
