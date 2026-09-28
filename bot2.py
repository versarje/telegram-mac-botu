import os
import time
import requests
import threading
from flask import Flask
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# ================= ==========================================
# 1. RENDER HEALTH CHECK / WEB SUNUCUSU (502'yi Kesin Engeller)
# ================= ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Telegram Futbol Analiz Botu Aktif ve Calisiyor!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)

# Web sunucusunu Anında Başlat
flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

# ================= ==========================================
# 2. TELEGRAM VE BELLEK (HAFIZA) AYARLARI
# ================= ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8894398415:AAEY_ffz8iPL8qZ8vJq3bgat7cibeQFhvI8")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-1003991937105")

hafiza_maclar = []
last_update_id = 0

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

# ================= ==========================================
# 3. VERİ ÇEKME VE TAHMİN / HAFIZAYA ALMA
# ================= ==========================================
def daily_match_fetch():
    global hafiza_maclar
    print("Günün maçları çekiliyor ve hafızaya alınıyor...", flush=True)
    
    yeni_hafiza = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            page.goto("https://www.flashscore.com", timeout=60000)
            page.wait_for_timeout(3000)
            
            html = page.content()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Örnek maç verileri (Veri çekme mantığınıza göre özelleştirebilirsiniz)
            ornek_maclar = [
                {
                    "ev_sahibi": "Galatasaray",
                    "deplasman": "Fenerbahçe",
                    "saat": "20:00",
                    "tahmin": "2.5 Üst / Karşılıklı Gol Var",
                    "guven": "%85"
                },
                {
                    "ev_sahibi": "Real Madrid",
                    "deplasman": "Barcelona",
                    "saat": "22:00",
                    "tahmin": "Ev Sahibi Kazanır (MS 1)",
                    "guven": "%78"
                }
            ]
            
            yeni_hafiza = ornek_maclar
            browser.close()
            
    except Exception as e:
        print(f"Günlük veri çekme hatası: {e}", flush=True)
            
    hafiza_maclar = yeni_hafiza
    print(f"Hafızaya toplam {len(hafiza_maclar)} maç kaydedildi.", flush=True)

def format_hafiza_mesaji():
    if not hafiza_maclar:
        return "⚠️ <b>Hafızada henüz kayıtlı bir maç tahmini bulunmuyor veya maçlar yükleniyor...</b>"
    
    mesaj = "📋 <b>GÜNÜN MAÇ TAHMİNLERİ VE BÜLTENİ</b> 📋\n\n"
    for i, mac in enumerate(hafiza_maclar, 1):
        mesaj += (
            f"{i}. ⚽ <b>{mac['ev_sahibi']} vs {mac['deplasman']}</b>\n"
            f"⏱ <b>Saat:</b> {mac['saat']}\n"
            f"🎯 <b>Tahmin:</b> {mac['tahmin']}\n"
            f"🔥 <b>Güven Oranı:</b> {mac['guven']}\n"
            f"-----------------------------------\n"
        )
    return mesaj

# ================= ==========================================
# 4. TELEGRAM DINLEYICI (!b KOMUTU)
# ================= ==========================================
def check_telegram_updates():
    global last_update_id
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={last_update_id + 1}&timeout=3"
    
    try:
        res = requests.get(url, timeout=5).json()
        if res.get("ok") and res.get("result"):
            for update in res["result"]:
                last_update_id = update["update_id"]
                
                message_data = update.get("message", {})
                text = message_data.get("text", "").strip()
                chat_id = message_data.get("chat", {}).get("id")
                
                if text.lower() == "!b" and chat_id:
                    print(f"!b komutu algılandı (Chat ID: {chat_id})", flush=True)
                    rapor = format_hafiza_mesaji()
                    send_telegram_message(chat_id, rapor)
                    
    except Exception as e:
        pass

# ================= ==========================================
# 5. ARKA PLAN GÖREV DÖNGÜSÜ
# ================= ==========================================
def background_worker():
    print("Bot arka plan işçisi başlatıldı.", flush=True)
    
    # Maçları arka planda çek (Flask kilitlenmesin diye)
    daily_match_fetch()
    
    son_gunluk_cekme = time.time()
    GUNLUK_SURE = 86400  # 24 Saat
    
    while True:
        try:
            check_telegram_updates()
            
            if time.time() - son_gunluk_cekme >= GUNLUK_SURE:
                daily_match_fetch()
                son_gunluk_cekme = time.time()
                
        except Exception as e:
            print(f"Arka plan döngü hatası: {e}", flush=True)
            
        time.sleep(2)

if __name__ == "__main__":
    # Veri çekme ve Telegram dinleme işlerini ARAYA GİRMEDEN başka bir thread'de çalıştır
    worker_thread = threading.Thread(target=background_worker, daemon=True)
    worker_thread.start()
    
    # Ana thread'i açık tut
    while True:
        time.sleep(3600)
