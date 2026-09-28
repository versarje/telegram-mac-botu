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
    # Render'ın dinamik portunu alır, yoksa 10000 kullanır
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)

# Web sunucusunu arka planda başlat
flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()
time.sleep(2)  # Portun dinlemeye geçmesi için kısa bir bekleme

# ================= ==========================================
# 2. TELEGRAM VE API AYARLARI
# ================= ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID")

gonderilen_maclar = set()  # Bildirimi atılan maçları tekrar atmamak için liste

def send_telegram_message(message):
    """Telegram kanalına/sohbetine mesaj gönderir."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Telegram mesaj gönderme hatası: {e}")
        return None

# ================= ==========================================
# 3. VERİ ÇEKME VE ANALİZ FONKSİYONLARI
# ================= ==========================================
def fetch_live_matches():
    """Playwright kullanarak canlı maç verilerini ve istatistiklerini çeker."""
    matches_data = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            # Örnek hedef analiz platformu veya Flashscore/Sofascore yönlendirmesi
            page.goto("https://www.flashscore.com", timeout=60000)
            page.wait_for_timeout(3000)
            
            # HTML içeriğini alma ve BeautifulSoup ile işleme
            html = page.content()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Maç tarama ve veri ayıklama mantığınız
            # (Web sitesinin selector yapısına göre veriler toplanır)
            
        except Exception as e:
            print(f"Veri çekme sırasında hata oluştu: {e}")
        finally:
            browser.close()
            
    return matches_data

def calculate_xg_and_stats(match):
    """
    Maç içi istatistikleri ve xG değerlerini değerlendirir.
    Kriterlere uyuyorsa True ve mesaj içeriği döndürür.
    """
    # Örnek Analiz Kriterleri:
    # Dakika 15-75 arası, Toplam xG > 1.2, İki takımın toplam şutu > 8
    
    match_id = match.get("id")
    home_team = match.get("home_team", "Ev Sahibi")
    away_team = match.get("away_team", "Deplasman")
    minute = match.get("minute", 0)
    score = match.get("score", "0-0")
    
    home_xg = match.get("home_xg", 0.0)
    away_xg = match.get("away_xg", 0.0)
    total_xg = home_xg + away_xg
    
    total_shots = match.get("total_shots", 0)

    # Bildirim Kriteri Kontrolü
    if match_id not in gonderilen_maclar:
        if 15 <= minute <= 75 and total_xg >= 1.2 and total_shots >= 8:
            
            msg = (
                f"🚨 <b>CANLI MAÇ ALARMI</b> 🚨\n\n"
                f"⚽ <b>{home_team} vs {away_team}</b>\n"
                f"⏱ <b>Dakika:</b> {minute}' | <b>Skor:</b> {score}\n\n"
                f"📊 <b>xG Değerleri:</b> {home_xg:.2f} - {away_xg:.2f} (Toplam: {total_xg:.2f})\n"
                f"🎯 <b>Toplam Şut:</b> {total_shots}\n\n"
                f"💡 <i>Yüksek gol beklentisi ve şut baskısı tespit edildi!</i>"
            )
            gonderilen_maclar.add(match_id)
            return True, msg

    return False, ""

# ================= ==========================================
# 4. BOTUN ANA DÖNGÜSÜ
# ================= ==========================================
def main_loop():
    """Canlı maçları sürekli kontrol eden ana döngü."""
    print("Bot döngüsü başlatıldı. Canlı maçlar izleniyor...")
    
    while True:
        try:
            print("Canlı maçlar taranıyor...")
            matches = fetch_live_matches()
            
            for match in matches:
                should_send, message = calculate_xg_and_stats(match)
                if should_send:
                    send_telegram_message(message)
                    print(f"Bildirim gönderildi: {match.get('home_team')} vs {match.get('away_team')}")
                    
        except Exception as e:
            print(f"Ana döngüde hata: {e}")
            
        # 60 saniyede bir tekrar tara
        time.sleep(60)

if __name__ == "__main__":
    main_loop()
