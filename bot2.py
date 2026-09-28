import os
import time
import re
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
    return "Google Spor Widget Botu Aktif!"

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
# 3. GOOGLE ARAMA WIDGET'INDAN MAÇLARI DETAYLI ÇEKME
# ================= ==========================================
def daily_match_fetch():
    global hafiza_maclar
    print("Google Arama Spor Widget'ına bağlanılıyor...", flush=True)
    
    yeni_hafiza = []
    
    try:
        with sync_playwright() as p:
            # Playwright masaüstü Chrome profili simülasyonu
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                locale="tr-TR",
                viewport={'width': 1366, 'height': 768}
            )
            page = context.new_page()
            
            # Google Türkiye Futbol Maçları Arama Bağlantısı
            google_url = "https://www.google.com/search?q=futbol+ma%C3%A7lar%C4%B1+bug%C3%BCn&hl=tr&gl=tr"
            page.goto(google_url, timeout=60000, wait_until="networkidle")
            
            # Dinamik widget bileşenlerinin yüklenmesini bekle
            time.sleep(4)
            
            html = page.content()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Katman 1: Google Spor Kartı İçindeki Takım Alanları
            teams_raw = [t.text.strip() for t in soup.find_all(attrs={"data-df-team-name": True})]
            
            # Katman 2: Klasik Google Spor Kapsayıcıları
            if not teams_raw:
                teams_raw = [t.text.strip() for t in soup.select('div.imso_mh__first-tn-blk, div.imso_mh__second-tn-blk, div.imso-g-first-team-name, div.imso-g-second-team-name, span.imso_mh__ft-name, span.imso_mh__st-name')]
            
            # Katman 3: Genel Tablo / Maç Satırları
            if not teams_raw:
                team_elements = soup.select('div.ellipsisize, span.ellipsisize')
                teams_raw = [t.text.strip() for t in team_elements if len(t.text.strip()) > 2]

            times_raw = [s.text.strip() for s in soup.select('div.imso_mh__status-or-time, span.imso_mh__ft-mt-m, div.imso-g-time, span.imso_post__time, div.imso_mh__scr-sb')]

            # Çekilen Takımları Eşleştirme (Çiftler Halinde)
            i = 0
            while i < len(teams_raw) - 1:
                ev = teams_raw[i]
                dep = teams_raw[i+1]
                
                # Gereksiz/Tekrarlanan Metin Temizliği
                if ev != dep and len(ev) > 1 and len(dep) > 1:
                    saat_idx = i // 2
                    saat = times_raw[saat_idx] if saat_idx < len(times_raw) else "Bugün"
                    
                    yeni_hafiza.append({
                        "ev_sahibi": ev,
                        "deplasman": dep,
                        "saat": saat,
                        "tahmin": "2.5 Üst / Karşılıklı Gol Var"
                    })
                    i += 2
                else:
                    i += 1

            browser.close()
            
    except Exception as e:
        print(f"Google Widget verisi çekilirken hata oluştu: {e}", flush=True)
        
    hafiza_maclar = yeni_hafiza
    print(f"Google Widget üzerinden hafızaya toplam {len(hafiza_maclar)} maç kaydedildi.", flush=True)

# ================= ==========================================
# 4. ARKA PLAN DÖNGÜSÜ
# ================= ==========================================
def background_worker():
    daily_match_fetch()
    
    # Başlangıç bildirimi gönder
    status_msg = f"🤖 <b>Bot aktif edildi!</b>\nGoogle Spor Widget'ından {len(hafiza_maclar)} maç hafızaya alındı.\nGruba <code>!b</code> yazarak bülteni çağırabilirsiniz."
    send_telegram_message(TELEGRAM_CHAT_ID, status_msg)
    
    son_gunluk_cekme = time.time()
    while True:
        # 12 saatte bir hafızayı tazele
        if time.time() - son_gunluk_cekme >= 43200:
            daily_match_fetch()
            son_gunluk_cekme = time.time()
        time.sleep(60)

if __name__ == "__main__":
    worker_thread = threading.Thread(target=background_worker, daemon=True)
    worker_thread.start()
    
    while True:
        time.sleep(3600)
