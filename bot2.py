import os
import time
import csv
import io
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
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        response = requests.post(url, json=payload, timeout=15)
        return response.json()
    except Exception as e:
        print(f"Telegram mesaj gönderme hatası: {e}", flush=True)
        return None

def send_telegram_document(chat_id, file_bytes, filename, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    files = {"document": (filename, file_bytes, "text/csv")}
    data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
    try:
        response = requests.post(url, data=data, files=files, timeout=30)
        print(f"Telegram dosya yanıtı: {response.status_code}", flush=True)
    except Exception as e:
        print(f"Telegram dosya gönderme hatası: {e}", flush=True)

def generate_and_send_csv(chat_id):
    if not hafiza_maclar:
        send_telegram_message(chat_id, "⚠️ <b>Henüz hafızada kaydedilmiş maç bulunamadı...</b>")
        return

    # CSV verisini bellekte (in-memory) oluşturuyoruz
    output = io.StringIO()
    # Excel'in Türkçe karakterleri (UTF-8 with BOM) doğrudan düzgün okuması için ekleme
    output.write('\ufeff')
    
    writer = csv.writer(output, delimiter=';')
    # Afilli başlık satırı
    writer.writerow(['Sira', 'Ev Sahibi', 'Deplasman', 'Saat / Durum', 'Ozel Tahmin'])
    
    for i, mac in enumerate(hafiza_maclar, 1):
        writer.writerow([
            i, 
            mac['ev_sahibi'], 
            mac['deplasman'], 
            mac['saat'], 
            mac['tahmin']
        ])
    
    csv_bytes = output.getvalue().encode('utf-8-sig')
    output.close()
    
    tarih_str = time.strftime("%d-%m-%Y")
    filename = f"Gunun_Maclari_{tarih_str}.csv"
    caption = f"📊 <b>GÜNÜN MAÇ BÜLTENİ VE TAHMİNLERİ</b>\n📅 Tarih: {tarih_str}\n⚽ Toplam Maç: <b>{len(hafiza_maclar)}</b>\n\n<i>Dosyayı Excel veya Google Sheets ile açarak detaylı inceleyebilirsiniz.</i>"
    
    send_telegram_document(chat_id, csv_bytes, filename, caption)

# ================= ==========================================
# 2. FLASK SERVER VE TELEGRAM WEBHOOK
# ================= ==========================================
@app.route('/')
def home():
    return "Google Spor Widget Botu (CSV Modu) Aktif!"

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    if update and "message" in update:
        message_data = update["message"]
        text = message_data.get("text", "").strip()
        chat_id = message_data.get("chat", {}).get("id")
        
        if text.lower() == "!b" and chat_id:
            print(f"!b komutu algılandı (Chat ID: {chat_id})", flush=True)
            generate_and_send_csv(chat_id)
            
    return jsonify({"status": "ok"}), 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)

flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

# ================= ==========================================
# 3. VERİ ÇEKME FONKSİYONU
# ================= ==========================================
def daily_match_fetch():
    global hafiza_maclar
    print("Google Spor Arama Widget'ına veri isteği atılıyor...", flush=True)
    
    yeni_hafiza = []
    
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
    except Exception as e:
        print(f"Veri çekme hatası: {e}", flush=True)

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
    daily_match_filter = daily_match_fetch()
    
    status_msg = f"🤖 <b>Bot2 (CSV Modu) Aktif Edildi!</b>\nGünün bülteninden <b>{len(hafiza_maclar)} maç</b> hafızaya alındı.\nGruba <code>!b</code> yazarak afilli CSV bültenini indirebilirsiniz."
    send_telegram_message(TELEGRAM_CHAT_ID, status_msg)
    
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
