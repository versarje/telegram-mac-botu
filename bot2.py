import os
import time
import requests
import threading
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

app = Flask(__name__)

# ================= ==========================================
# 1. TELEGRAM VE HAFIZA AYARLARI
# ================= ==========================================
TELEGRAM_BOT_TOKEN = "8894398415:AAEY_ffz8iPL8qZ8vJq3bgat7cibeQFhvI8"
TELEGRAM_CHAT_ID = "-1003991937105"

hafiza_maclar = []

def send_telegram_message(chat_id, message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Telegram mesaj gönderme hatası: {e}", flush=True)
        return None

def send_telegram_photo(chat_id, photo_bytes, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    files = {"photo": ("screenshot.png", photo_bytes, "image/png")}
    data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
    try:
        requests.post(url, data=data, files=files, timeout=20)
    except Exception as e:
        print(f"Telegram fotoğraf gönderme hatası: {e}", flush=True)

def format_hafiza_mesaji():
    if not hafiza_maclar:
        return "⚠️ <b>Google üzerindeki bugünün maçları taranıyor veya henüz maç bulunamadı...</b>"
    
    mesaj = "📋 <b>GOOGLE SPOR WİDGET - GÜNÜN MAÇLARI VE TAHMİNLERİ</b> 📋\n\n"
    for i, mac in enumerate(hafiza_maclar, 1):
        mesaj += (
            f"{i}. ⚽ <b>{mac['ev_sahibi']} vs {mac['deplasman']}</b>\n"
            f"⏱ <b>Saat / Durum:</b> {mac['saat']}\n"
            f"🎯 <b>Tahmin:</b> {mac['tahmin']}\n"
            f"-----------------------------------\n"
        )
    return mesaj

# ================= ==========================================
# 2. RENDER HEALTH CHECK VE TELEGRAM WEBHOOK
# ================= ==========================================
@app.route('/')
def home():
    return "Google Spor Widget Botu (Debug Modu) Aktif!"

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    if update and "message" in update:
        message_data = update["message"]
        text = message_data.get("text", "").strip()
        chat_id = message_data.get("chat", {}).get("id")
        
        if text.lower() == "!b" and chat_id:
            print(f"!b komutu algılandı (Chat ID: {chat_id})", flush=True)
            rapor = format_hafiza_mesaji()
            send_telegram_message(chat_id, rapor)
            
    return jsonify({"status": "ok"}), 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)

flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

# ================= ==========================================
# 3. GOOGLE WIDGET DEBUG VE VERİ ÇEKME FONKSİYONU
# ================= ==========================================
def daily_match_fetch():
    global hafiza_maclar
    print("Google Arama Spor Widget'ına bağlanılıyor (DEBUG)...", flush=True)
    
    yeni_hafiza = []
    debug_log = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                locale="tr-TR",
                viewport={'width': 1280, 'height': 800}
            )
            page = context.new_page()
            
            google_url = "https://www.google.com/search?q=bugün+oynanacak+futbol+maçları&hl=tr&gl=tr"
            page.goto(google_url, timeout=60000)
            time.sleep(5)
            
            # --- DEBUG BİLGİLERİ ---
            page_title = page.title()
            screenshot_bytes = page.screenshot(full_page=False)
            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            debug_log.append(f"📌 <b>Sayfa Başlığı:</b> {page_title}")
            debug_log.append(f"🔗 <b>URL:</b> {page.url}")
            
            # Google Güvenlik / CAPTCHA Kontrolü
            if "recaptcha" in html_content.lower() or "sorry/index" in page.url.lower():
                debug_log.append("🚨 <b>TEŞHİS:</b> Google IP'yi engelledi (CAPTCHA / Robot Kontrolü çıktı)!")
            else:
                # Element Kontrolleri
                imso_count = len(soup.select('div.imso-g-board, div.imso_mh__match-row, div.K1q38b'))
                team_count = len(soup.select('div[data-df-team-name], div.imso_mh__first-tn-blk, div.imso-g-first-team-name'))
                
                debug_log.append(f"🔍 <b>Aramada Bulunan Widget Kart Sayısı:</b> {imso_count}")
                debug_log.append(f"⚽ <b>Bulunan Takım Element Sayısı:</b> {team_count}")
                
                # Takımları çekmeyi dene
                home_teams = [t.text.strip() for t in soup.select('div[data-df-team-name], div.imso_mh__first-tn-blk, div.imso-g-first-team-name')]
                away_teams = [t.text.strip() for t in soup.select('div.imso_mh__second-tn-blk, div.imso-g-second-team-name')]
                times = [s.text.strip() for s in soup.select('div.imso_mh__status-or-time, span.imso_mh__ft-mt-m, div.imso-g-time')]
                
                min_len = min(len(home_teams), len(away_teams))
                for i in range(min_len):
                    yeni_hafiza.append({
                        "ev_sahibi": home_teams[i],
                        "deplasman": away_teams[i],
                        "saat": times[i] if i < len(times) else "Bugün",
                        "tahmin": "2.5 Üst / KG Var"
                    })
            
            browser.close()
            
            # Telegram'a Ekran Görüntüsü ve Debug Raporunu Gönder
            debug_text = "🛠 <b>GOOGLE WIDGET DEBUG RAPORU</b> 🛠\n\n" + "\n".join(debug_log)
            send_telegram_photo(TELEGRAM_CHAT_ID, screenshot_bytes, debug_text)

    except Exception as e:
        err_msg = f"❌ <b>Debug Hatası:</b> {str(e)}"
        print(err_msg, flush=True)
        send_telegram_message(TELEGRAM_CHAT_ID, err_msg)
        
    hafiza_maclar = yeni_hafiza
    print(f"Debug işlemi bitti. Hafızaya {len(hafiza_maclar)} maç kaydedildi.", flush=True)

# ================= ==========================================
# 4. ARKA PLAN DÖNGÜSÜ
# ================= ==========================================
def background_worker():
    daily_match_fetch()
    
    son_gunluk_cekme = time.time()
    while True:
        if time.time() - son_gunluk_cekme >= 43200:
            daily_match_fetch()
            son_gunluk_cekme = time.time()
        time.sleep(60)

if __name__ == "__main__":
    worker_thread = threading.Thread(target=background_worker, daemon=True)
    worker_thread.start()
    
    while True:
        time.sleep(3600)
