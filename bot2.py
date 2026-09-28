import os
import time
import requests
import threading
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup

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
        response = requests.post(url, json=payload, timeout=15)
        print(f"Telegram yanıtı: {response.status_code}", flush=True)
        return response.json()
    except Exception as e:
        print(f"Telegram mesaj gönderme hatası: {e}", flush=True)
        return None

def format_hafiza_mesaji():
    if not hafiza_maclar:
        return "⚠️ <b>Günün maçları taranıyor veya Google üzerinde henüz veri bulunamadı...</b>"
    
    mesaj = f"📋 <b>GÜNÜN MAÇLARI VE TAHMİNLERİ ({len(hafiza_maclar)} Maç)</b> 📋\n\n"
    for i, mac in enumerate(hafiza_maclar, 1):
        mesaj += (
            f"{i}. ⚽ <b>{mac['ev_sahibi']} vs {mac['deplasman']}</b>\n"
            f"⏱ <b>Saat / Durum:</b> {mac['saat']}\n"
            f"🎯 <b>Tahmin:</b> {mac['tahmin']}\n"
            f"-----------------------------------\n"
        )
    return mesaj

# ================= ==========================================
# 2. FLASK SERVER VE TELEGRAM WEBHOOK
# ================= ==========================================
@app.route('/')
def home():
    return "Google Spor Widget Botu (bot2.py) Aktif ve Çalışıyor!"

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
# 3. KESİNTİSİZ VERİ ÇEKME FONKSİYONU (Requests + BS4)
# ================= ==========================================
def daily_match_fetch():
    global hafiza_maclar
    print("Google Spor Arama Widget'ına veri isteği atılıyor...", flush=True)
    
    yeni_hafiza = []
    
    # Google'ı gerçek bir masaüstü tarayıcısı gibi taklit eden başlıklar
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    
    google_url = "https://www.google.com/search?q=bug%C3%BCn+oynanacak+futbol+ma%C3%A7lar%C4%B1&hl=tr&gl=tr"
    
    try:
        response = requests.get(google_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Google Spor Widget CSS Sınıfları
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
        else:
            print(f"Google yanıt vermedi, HTTP Kodu: {response.status_code}", flush=True)

    except Exception as e:
        print(f"Veri çekme hatası: {e}", flush=True)

    # Eğer Google HTML yanıtında sınıflar değişmişse ve 0 maç döndüyse yedek API'yi devreye al
    if not yeni_hafiza:
        print("Google alternatif yönteme geçiliyor...", flush=True)
        try:
            today_str = time.strftime("%Y-%m-%d")
            backup_url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={today_str.replace('-', '')}"
            res = requests.get(backup_url, timeout=10)
            if res.status_code == 200:
                events = res.json().get("events", [])
                for event in events:
                    competitors = event.get("competitions", [{}])[0].get("competitors", [])
                    if len(competitors) >= 2:
                        ev = competitors[0].get("team", {}).get("displayName", "")
                        dep = competitors[1].get("team", {}).get("displayName", "")
                        saat = event.get("status", {}).get("type", {}).get("shortDetail", "Bugün")
                        
                        yeni_hafiza.append({
                            "ev_sahibi": ev,
                            "deplasman": dep,
                            "saat": saat,
                            "tahmin": "KG Var / 2.5 Üst"
                        })
        except Exception as e:
            print(f"Yedek servis hatası: {e}", flush=True)

    hafiza_maclar = yeni_hafiza
    print(f"İşlem tamamlandı. Hafızaya {len(hafiza_maclar)} maç kaydedildi.", flush=True)

# ================= ==========================================
# 4. ARKA PLAN DÖNGÜSÜ
# ================= ==========================================
def background_worker():
    daily_match_fetch()
    
    # Başlangıç bildirimi gönder
    status_msg = f"🤖 <b>Bot2 Aktif Edildi!</b>\nGünün bülteninden <b>{len(hafiza_maclar)} maç</b> hafızaya alındı.\nGruba <code>!b</code> yazarak bülteni çağırabilirsiniz."
    send_telegram_message(TELEGRAM_CHAT_ID, status_msg)
    
    son_gunluk_cekme = time.time()
    while True:
        # 12 saatte bir hafızayı güncelle
        if time.time() - son_gunluk_cekme >= 43200:
            daily_match_fetch()
            son_gunluk_cekme = time.time()
        time.sleep(60)

if __name__ == "__main__":
    worker_thread = threading.Thread(target=background_worker, daemon=True)
    worker_thread.start()
    
    while True:
        time.sleep(3600)
