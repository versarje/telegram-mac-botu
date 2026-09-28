import os
import time
import requests
import threading
from flask import Flask
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# ================= ==========================================
# 1. RENDER HEALTH CHECK / WEB SUNUCUSU (502 Önleyici)
# ================= ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Telegram Futbol Analiz Botu Aktif ve Calisiyor!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)

# Web sunucusunu arka planda başlat
flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()
time.sleep(2)

# ================= ==========================================
# 2. TELEGRAM VE BELLEK (HAFIZA) AYARLARI
# ================= ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID")

# Maçların ve tahminlerin tutulacağı küresel bellek (hafıza)
hafiza_maclar = []
last_update_id = 0  # Telegram mesajlarını okurken son okunan mesaj ID'si

def send_telegram_message(chat_id, message):
    """Belirtilen chat_id'ye Telegram mesajı gönderir."""
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
    """Günün maçlarını çeker, tahminleri yapar ve hafızaya kaydeder."""
    global hafiza_maclar
    print("Günün maçları çekiliyor ve hafızaya alınıyor...", flush=True)
    
    yeni_hafiza = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            # Hedef maç/istatistik web sitesi
            page.goto("https://www.flashscore.com", timeout=60000)
            page.wait_for_timeout(3000)
            
            html = page.content()
            soup = BeautifulSoup(html, 'html.parser')
            
            # TODO: Siteden bugünün maçlarını çekme mantığınız.
            # Örnek simüle edilmiş veri yapısı:
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
            print(f"Hafızaya toplam {len(yeni_hafiza)} maç kaydedildi.", flush=True)
            
        except Exception as e:
            print(f"Günlük veri çekme hatası: {e}", flush=True)
        finally:
            browser.close()
            
    hafiza_maclar = yeni_hafiza

def format_hafiza_mesaji():
    """Hafızadaki maçları Telegram için rapor formatına getirir."""
    if not hafiza_maclar:
        return "⚠️ <b>Hafızada henüz kayıtlı bir maç tahmini bulunmuyor.</b>"
    
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
    """Telegram'a gelen yeni mesajları kontrol eder ve !b komutunu yanıtlar."""
    global last_update_id
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={last_update_id + 1}&timeout=5"
    
    try:
        res = requests.get(url, timeout=10).json()
        if res.get("ok") and res.get("result"):
            for update in res["result"]:
                last_update_id = update["update_id"]
                
                message_data = update.get("message", {})
                text = message_data.get("text", "").strip()
                chat_id = message_data.get("chat", {}).get("id")
                
                # Kullanıcı !b komutunu attığında
                if text.lower() == "!b" and chat_id:
                    print(f"!b komutu algılandı (Chat ID: {chat_id})", flush=True)
                    rapor = format_hafiza_mesaji()
                    send_telegram_message(chat_id, rapor)
                    
    except Exception as e:
        print(f"Telegram güncelleme kontrol hatası: {e}", flush=True)

# ================= ==========================================
# 5. ZAMANLAYICI VE DÖNGÜ (MAIN LOOP)
# ================= ==========================================
def main_loop():
    print("Bot başlatıldı. Günlük bülten ve !b komut dinleyici aktif.", flush=True)
    
    # Bot ilk açıldığında 1 kere maçları çekip hafızaya alsın
    daily_match_fetch()
    
    son_gunluk_cekme = time.time()
    GUNLUK_SURE = 86400  # 24 Saat (saniye cinsinden)
    
    while True:
        try:
            # 1. Telegram'a !b yazıldı mı kontrol et (Her saniye)
            check_telegram_updates()
            
            # 2. 24 Saat dolduysa maçları tekrar çekip hafızayı güncelle
            if time.time() - son_gunluk_cekme >= GUNLUK_SURE:
                daily_match_fetch()
                son_gunluk_cekme = time.time()
                
        except Exception as e:
            print(f"Ana döngü hatası: {e}", flush=True)
            
        time.sleep(2)  # Sunucuyu yormamak için 2 saniyede bir kontrol et

if __name__ == "__main__":
    main_loop()
