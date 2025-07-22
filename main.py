import requests, time, random, json, os
from bs4 import BeautifulSoup
from urllib.parse import quote
from fake_useragent import UserAgent
from datetime import datetime
import telegram
import asyncio

# CONFIGURAZIONI
AFFILIATE_TAG = "pokemonbundle-21"
PRINCIPALI = [
    "151",
    "Evoluzioni prismatiche",
    "Rivali predestinati",
    "Origine perduta",
    "Evoluzioni eteree",
    "Astri lucenti",
    "Tempesta argentata"
]

TIPOLOGIE = [
    "Collezioni",
    "Blister",
    "Box",
    "Etb",
    "Dispenser",
    "Tin",
    "Mini tin"
]

RICERCHE_SINGOLE = [
    "Pokémon GCC set allenatore",
    "Pokémon GCC italiano set allenatori",
    "Pokémon Allenatore Fuoriclasse",
    "Pokémon TCG Violet Scatola Allenatore",
]

SEARCH_TERMS = [f"pokemon {p} {t}".strip() for p in PRINCIPALI for t in TIPOLOGIE] + RICERCHE_SINGOLE
DATABASE_FILE = "prodotti_database.json"

PAROLE_CHIAVE = ["pokemon", "pokémon", "scarlatto", "violetto", "booster", "collezione", "allenatore", "fuoriclasse", "tcg", "scatola", "GCC"]

def get_headers():
    ua = UserAgent()
    return {
        "User-Agent": ua.random,
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8",
        "Referer": "https://www.google.com"
    }

def estrai_prodotti(search_term):
    url = f"https://www.amazon.it/s?k={quote(search_term)}"
    res = requests.get(url, headers=get_headers())
    soup = BeautifulSoup(res.text, "lxml")

    prodotti = []
    for item in soup.select('[data-asin]'):
        asin = item["data-asin"]
        if not asin:
            continue
        titolo_el = item.select_one("h2 span")
        prezzo_el = item.select_one(".a-price .a-offscreen")
        img_el = item.select_one("img")

        if titolo_el and prezzo_el and img_el:
            titolo = titolo_el.text.strip()
            # FILTRO: accetta solo se almeno una parola chiave è nel titolo
            if not any(kw.lower() in titolo.lower() for kw in PAROLE_CHIAVE):
                continue
            prezzo = prezzo_el.text.strip()
            img_url = img_el.get("src")
            link_affiliato = (
                f"https://www.amazon.it/dp/{asin}/?tag={AFFILIATE_TAG}"
            )
            prodotti.append((asin, titolo, prezzo, img_url, link_affiliato))
    return prodotti

def carica_database():
    """Carica il database dei prodotti salvati"""
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def salva_database(database):
    """Salva il database dei prodotti"""
    with open(DATABASE_FILE, 'w', encoding='utf-8') as f:
        json.dump(database, f, ensure_ascii=False, indent=2)


def estrai_prezzo_numerico(prezzo_str):
    """Estrae il valore numerico dal prezzo"""
    import re
    # Rimuove tutto tranne numeri, virgole e punti
    numeri = re.findall(r'[\d.,]+', prezzo_str)
    if numeri:
        # Prende il primo numero trovato e lo converte
        numero = numeri[0].replace(',', '.')
        try:
            return float(numero)
        except ValueError:
            return None
    return None


def confronta_e_filtra_prodotto(asin, titolo, prezzo, img_url, link, database):
    timestamp = datetime.now().isoformat()
    prezzo_numerico = estrai_prezzo_numerico(prezzo)
    prodotto_id = asin

    if prodotto_id in database:
        vecchio_prodotto = database[prodotto_id]
        vecchio_prezzo = vecchio_prodotto.get('prezzo_numerico')
        vecchio_prezzo_str = vecchio_prodotto.get('prezzo')
        era_non_disponibile = vecchio_prodotto.get('non_disponibile', False)

        # DEBUG: stampa il prodotto nel database e quello trovato ora
        print("\n--- DEBUG CONFRONTO ---")
        print("PRODOTTO NEL DATABASE:")
        print(json.dumps(vecchio_prodotto, indent=2, ensure_ascii=False))
        print("PRODOTTO TROVATO ORA:")
        print(json.dumps({
            'asin': asin,
            'titolo': titolo,
            'prezzo': prezzo,
            'prezzo_numerico': prezzo_numerico,
            'img_url': img_url,
            'link': link
        }, indent=2, ensure_ascii=False))
        print("--- FINE DEBUG ---\n")

        if era_non_disponibile and prezzo_numerico is not None:
            stato = 'TORNA_DISPONIBILE'
            messaggio = f"🔥 PRODOTTO TORNATO DISPONIBILE! 🔥\nEra non disponibile, ora costa {prezzo}"
        elif (prezzo_numerico is not None and vecchio_prezzo is not None and prezzo_numerico < vecchio_prezzo):
            risparmio = vecchio_prezzo - prezzo_numerico
            if risparmio < 2:
                # Non notificare cali di prezzo inferiori a 2 euro
                stato = None
                messaggio = None
            else:
                stato = 'CALO_PREZZO'
                shock = " 😱" if risparmio >= 20 else ""
                messaggio = f"CALO DI PREZZO! 💰{shock}\nDa {vecchio_prezzo_str} a {prezzo}\nRisparmio: €{risparmio:.2f}"
        elif prezzo == vecchio_prezzo_str:
            # Nessuna novità, non inviare nulla
            return None
        else:
            # Aggiorna comunque il database
            stato = None
            messaggio = None

        # Aggiorna il database
        database[prodotto_id] = {
            'titolo': titolo,
            'prezzo': prezzo,
            'prezzo_numerico': prezzo_numerico,
            'img_url': img_url,
            'link': link,
            'ultimo_aggiornamento': timestamp,
            'non_disponibile': prezzo_numerico is None
        }

        if stato:
            return {
                'titolo': titolo,
                'prezzo': prezzo,
                'img_url': img_url,
                'link': link,
                'stato': stato,
                'messaggio': messaggio
            }
        else:
            return None

    else:
        # Nuovo prodotto
        database[prodotto_id] = {
            'titolo': titolo,
            'prezzo': prezzo,
            'prezzo_numerico': prezzo_numerico,
            'img_url': img_url,
            'link': link,
            'primo_rilevamento': timestamp,
            'ultimo_aggiornamento': timestamp,
            'non_disponibile': prezzo_numerico is None
        }
        return {
            'titolo': titolo,
            'prezzo': prezzo,
            'img_url': img_url,
            'link': link,
            'stato': 'NUOVO',
            'messaggio': f"🆕 NUOVO PRODOTTO TROVATO! 🆕"
        }

def genera_testo_offerta_avanzato(prodotto_info, search_term):
    """Genera il testo dell'offerta con informazioni aggiuntive e titoletto"""
    base_text = f"""🔎 *{search_term.title()}*

📦 *{prodotto_info['titolo']}*
💰 Prezzo: {prodotto_info['prezzo']}
🔗 {prodotto_info['link']}
"""
    if 'messaggio' in prodotto_info and prodotto_info['messaggio']:
        base_text = f"{prodotto_info['messaggio']}\n\n{base_text}"
    return base_text


async def invia_messaggio_telegram(testi_da_copiare, chat_id, token):
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
    bot = Bot(token=token)
    
    def escape_markdown(text):
        escape_chars = r"_*[]()~`>#+-=|{}.!"
        return ''.join(['\\' + c if c in escape_chars else c for c in text])
    
    for testo_con_link in testi_da_copiare:
        # Estrai il link dal testo
        lines = testo_con_link.split('\n')
        link_line = [line for line in lines if line.startswith('🔗')]
        if link_line:
            link_originale = link_line[0].replace('🔗 ', '').strip()
            # Crea link al carrello Amazon
            asin = link_originale.split('/dp/')[1].split('/')[0]
            link_carrello = f"https://www.amazon.it/gp/aws/cart/add.html?ASIN.1={asin}&Quantity.1=1&tag={AFFILIATE_TAG}"
            
            # Rimuovi la riga del link dal testo
            testo_senza_link = '\n'.join([line for line in lines if not line.startswith('🔗')])
            
            # Crea il bottone
            keyboard = [[InlineKeyboardButton("🛒 Acquista Subito", url=link_carrello)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await bot.send_message(
                chat_id=chat_id, 
                text=escape_markdown(testo_senza_link), 
                parse_mode="MarkdownV2",
                reply_markup=reply_markup
            )


def invia_messaggio_discord(testi_da_copiare, webhook_url):
    import requests
    
    messaggi_discord = []
    for testo_con_link in testi_da_copiare:
        # Estrai il link dal testo
        lines = testo_con_link.split('\n')
        link_line = [line for line in lines if line.startswith('🔗')]
        if link_line:
            link_originale = link_line[0].replace('🔗 ', '').strip()
            # Crea link al carrello Amazon
            asin = link_originale.split('/dp/')[1].split('/')[0]
            link_carrello = f"https://www.amazon.it/gp/aws/cart/add.html?ASIN.1={asin}&Quantity.1=1&tag={AFFILIATE_TAG}"
            
            # Rimuovi la riga del link dal testo e aggiungi bottone
            testo_senza_link = '\n'.join([line for line in lines if not line.startswith('🔗')])
            testo_con_bottone = f"{testo_senza_link}\n\n[🛒 **Acquista Subito**]({link_carrello})"
            messaggi_discord.append(testo_con_bottone)
    
    if messaggi_discord:
        testo_finale = "\n\n".join(messaggi_discord)
        data = {"content": testo_finale}
        response = requests.post(webhook_url, json=data)
        if response.status_code == 204:
            print("✅ Messaggio inviato su Discord!")
        else:
            print(f"❌ Errore invio Discord: {response.status_code} - {response.text}")


# LOOP PRINCIPALE
database = carica_database()

while True:
    testi_da_copiare = []
    for term in SEARCH_TERMS:
        risultati = estrai_prodotti(term)
        if risultati:
            asin, titolo, prezzo, img_url, link = risultati[0]
            prodotto_info = confronta_e_filtra_prodotto(asin, titolo, prezzo, img_url, link, database)
            if prodotto_info:
                testo = genera_testo_offerta_avanzato(prodotto_info, term)
                print(testo)
                testi_da_copiare.append(testo)
            else:
                print("Nessun nuovo prodotto o cambio prezzo rilevato.\n")
        else:
            print("Nessun prodotto trovato per questa ricerca.\n")

    salva_database(database)
    print("DEBUG - Database aggiornato:")
    print(json.dumps(database, indent=2, ensure_ascii=False))

    # Salva i risultati da copiare su WhatsApp in un file txt
    if testi_da_copiare:
        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"prodotti_whatsapp_{now}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n".join(testi_da_copiare))
        print(f"\n✅ File {filename} creato con i prodotti da condividere!")

        # INVIO SU TELEGRAM
        with open("config_secret.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        TELEGRAM_TOKEN = config["TELEGRAM_TOKEN"]
        TELEGRAM_CHAT_ID = config["TELEGRAM_CHAT_ID"]
        testo_telegram = "\n".join(testi_da_copiare)
        asyncio.run(invia_messaggio_telegram(testi_da_copiare, TELEGRAM_CHAT_ID, TELEGRAM_TOKEN))

        # INVIO SU DISCORD
        DISCORD_WEBHOOK_URL = config["DISCORD_WEBHOOK_URL"]
        testo_discord = "\n\n".join(testi_da_copiare)
        invia_messaggio_discord(testi_da_copiare, DISCORD_WEBHOOK_URL)
    else:
        print("\nℹ️ Nessun prodotto da condividere su WhatsApp.")

    print("\n✅ Scansione completata! Database aggiornato.")
    print("DEBUG - Database aggiornato:")
    print(json.dumps(database, indent=2, ensure_ascii=False))

    # --- LOGICA PER LA FREQUENZA ---
    ora = datetime.now().hour
    if 0 <= ora < 9:
        print("Attendo 2 ore prima della prossima scansione...\n")
        time.sleep(7200)  # 2 ore
    else:
        print("Attendo 5 minuti prima della prossima scansione...\n")
        time.sleep(300)  # 5 minuti