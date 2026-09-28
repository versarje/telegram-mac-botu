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
    return "Google Spor Widget Botu Aktif ve Çalışıyor!"

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
# 3. GOOGLE ARAMA WIDGET'INDAN CANLI / GÜNÜN MAÇLARINI ÇEKME
# ================= ==========================================
def daily_match_fetch():
    global hafiza_maclar
    print("Google Arama Spor Widget'ına bağlanılıyor...", flush=True)
    
    yeni_hafiza = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="tr-TR"
            )
            page = context.new_page()
            
            # Google TR üzerinde günün futbol maçları araması
            google_url = "https://www.google.com/search?q=bugün+oynanacak+futbol+maçları&hl=tr"
            page.goto(google_url, timeout=60000)
            
            # Google Widget öğelerinin yüklenmesini bekle
            page.wait_for_timeout(4000)
            
            html = page.content()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Google Spor Kartındaki Ev Sahibi ve Deplasman Takımları
            home_teams = [t.text.strip() for t in soup.select('div.imso_mh__first-tn-blk, div.imso-g-first-team-name, span.imso_mh__ft-name')]
            away_teams = [t.text.strip() for t in soup.select('div.imso_mh__second-tn-blk, div.imso-g-second-team-name, span.imso_mh__st-name')]
            times = [s.text.strip() for s in soup.select('div.imso_mh__status-or-time, span.imso_mh__ft-mt-m, div.imso-g-time')]

            # Takım isimleri eşleşiyorsa listeye ekle
            min_length = min(len(home_teams), len(away_teams))
            
            for i in range(min_length):
                ev = home_teams[i]
                dep = away_teams[i]
                saat = times[i] if i < len(times) else "Bugün"
                
                # Tahmin Algoritması / Şablonu
                tahmin = "2.5 Üst / Karşılıklı Gol Var"
                
                yeni_hafiza.append({
                    "ev_sahibi": ev,
                    "deplasman": dep,
                    "saat": saat,
                    "tahmin": tahmin
                })
                
            browser.close()
            
    except Exception as e:
        print(f"Google Widget verisi çekilirken hata oluştu: {e}", flush=True)
        
    hafiza_maclar = yeni_hafiza
    print(f"Google Widget üzerinden hafızaya toplam {len(hafiza_maclar)} maç kaydedildi.", flush=True)

# ================= ==========================================
# 4. ARKA PLAN DÖNGÜSÜ
# ================= ==========================================
def background_worker():
    # Bot açılır açılmaz Google Widget'ı tara
    daily_match_fetch()
    
    # Başlangıç bildirimi gönder
    send_telegram_message(TELEGRAM_CHAT_ID, "🤖 <b>Bot aktif edildi!</b>\nGoogle Spor Widget'ından maçlar hafızaya alındı. Gruba <code>!b</code> yazarak bülteni çağırabilirsiniz.")
    
    son_gunluk_cekme = time.time()
    while True:
        # 24 saatte bir hafızayı Google'dan güncelle (86400 saniye)
        if time.time() - son_gunluk_cekme >= 86400:
            daily_match_fetch()
            son_gunluk_cekme = time.time()
        time.sleep(60)

if __name__ == "__main__":
    worker_thread = threading.Thread(target=background_worker, daemon=True)
    worker_thread.start()
    
    while True:
        time.sleep(3600)
