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
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
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

def format_hafiza_mesaji():
    if not hafiza_maclar:
        return "⚠️ <b>Google üzerindeki bugünün maçları yükleniyor veya maç bulunamadı...</b>"
    
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
    return "Google Widget Maç Botu Aktif!"

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    if update and "message" in update:
        message_data = update["message"]
        text = message_data.get("text", "").strip()
        chat_id = message_data.get("chat", {}).get("id")
        
        if text.lower() == "!b" and chat_id:
            print(f"!b komutu Google Widget bülteni için algılandı (Chat ID: {chat_id})", flush=True)
            rapor = format_hafiza_mesaji()
            send_telegram_message(chat_id, rapor)
            
    return jsonify({"status": "ok"}), 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)

flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

# ================= ==========================================
# 3. GOOGLE SEARCH WIDGET'TAN MAÇLARI ÇEKME
# ================= ==========================================
def daily_match_fetch():
    global hafiza_maclar
    print("Google Arama Widget'ından günün maçları çekiliyor...", flush=True)
    
    yeni_hafiza = []
    
    try:
        with sync_playwright() as p:
            # Headless Chrome başlatıyoruz
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="tr-TR"
            )
            page = context.new_page()
            
            # Google'da bugünün maçları widget'ını getiren arama sorgusu
            google_url = "https://www.google.com/search?q=bugün+oynanacak+futbol+maçları&hl=tr"
            page.goto(google_url, timeout=60000)
            page.wait_for_timeout(3000)
            
            html = page.content()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Google Sports / Football Match Card / Widget kapsayıcıları
            # Google Widget maç kartı seçicileri (imso_mh / K1q38b / match-card sınıfları)
            match_cards = soup.find_all('div', class_=lambda c: c and ('imso-g' in c or 'K1q38b' in c or 'liveresults-sports-immersive' in c))
            
            # Eğer genel sınıfla bulunamazsa tüm widget satırlarını tara
            if not match_cards:
                match_cards = soup.select('tr.imso-g-table-row, div.imso-g-board')

            # Alternatif Selector: Google Spor Kartındaki Takım İsimleri
            team_names = [t.text.strip() for t in soup.select('div.imso_mh__first-tn-blk, div.imso_mh__second-tn-blk, span.ellipsisize')]
            time_statuses = [s.text.strip() for s in soup.select('div.imso_mh__status-or-time, span.imso_mh__ft-mt-m')]

            # Eşleştirme Yapma
            for i in range(0, len(team_names) - 1, 2):
                ev = team_names[i]
                dep = team_names[i+1]
                saat = time_statuses[i//2] if (i//2) < len(time_statuses) else "Bugün"
                
                # Tahmin oluşturucu
                tahmin = "2.5 Üst / KG Var"
                
                yeni_hafiza.append({
                    "ev_sahibi": ev,
                    "deplasman": dep,
                    "saat": saat,
                    "tahmin": tahmin
                })
                
            browser.close()
            
    except Exception as e:
        print(f"Google Widget veri çekme hatası: {e}", flush=True)
        
    hafiza_maclar = yeni_hafiza
    print(f"Google Widget'tan hafızaya toplam {len(hafiza_maclar)} maç kaydedildi.", flush=True)

# ================= ==========================================
# 4. ARKA PLAN İŞÇİSİ
# ================= ==========================================
def background_worker():
    daily_match_fetch()
    son_gunluk_cekme = time.time()
    
    while True:
        # 24 Saatte bir Google Widget'ı tekrar tara
        if time.time() - son_gunluk_cekme >= 86400:
            daily_match_fetch()
            son_gunluk_cekme = time.time()
        time.sleep(60)

if __name__ == "__main__":
    worker_thread = threading.Thread(target=background_worker, daemon=True)
    worker_thread.start()
    
    while True:
        time.sleep(3600)
