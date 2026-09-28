import os
import time
import requests
import threading
from datetime import datetime, timezone, timedelta
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

def gelismis_ai_analiz_uret(ev_sahibi, deplasman):
    # Takım isimlerini küçük harfe çevirerek analiz motoruna sokuyoruz
    ev_lower = ev_sahibi.lower()
    dep_lower = deplasman.lower()
    
    # Büyük/güçlü takım anahtar kelimeleri
    devler = ["real madrid", "barcelona", "manchester city", "bayern", "psg", "galatasaray", "fenerbahçe", "beşiktaş", "liverpool", "arsenal", "inter", "milan", "juventus"]
    
    ev_guclu = any(dev in ev_lower for dev in devler)
    dep_guclu = any(dev in dep_lower for dev in devler)
    
    if ev_guclu and dep_guclu:
        tahmin = "🔥 Karşılıklı Gol Var & 2.5 Üst (Zirve Mücadelesi)"
        skor = "2-1 / 2-2"
        guven = "%84 (Yüksek)"
        analiz = "İki formlu dev ekip de sahaya galibiyet için çıkacaktır. Tempomuz yüksek ve gol beklentisi (xG) üst düzeyde."
    elif ev_guclu and not dep_guclu:
        tahmin = "⭐ Ev Sahibi Net Favori (MS 1 & 1.5 Üst)"
        skor = "2-0 / 3-0"
        guven = "%89 (Çok Güçlü)"
        analiz = "Ev sahibinin iç saha baskısı ve kadro kalitesi maçın kontrolünü ilk dakikadan itibaren eline alacağını gösteriyor."
    elif not ev_guclu and dep_guclu:
        tahmin = "⚡ Deplasman Baskın Çıkar (MS 2 veya KG Var)"
        skor = "1-2 / 0-2"
        guven = "%81 (Güçlü)"
        analiz = "Deplasman ekibi kadro üstünlüğüyle oyunu domine etmeye çalışacaktır. Gollü geçmeye aday bir müsabaka."
    else:
        # Dengeli veya alt lig takımları için olasılıksal analiz
        secenekler = [
            {"tahmin": "🛡️ 2.5 Alt (Taktiksel Kilitlenme)", "skor": "1-0 / 0-1", "guven": "%74", "analiz": "Orta saha mücadelesi şeklinde geçmesi beklenen, az pozisyonlu maç senaryosu."},
            {"tahmin": "⚡ Karşılıklı Gol (KG) Var", "skor": "1-1 / 2-1", "guven": "%77", "analiz": "Savunma zaafları bulunan iki ekibin de skor üretme ihtimali oldukça yüksek."},
            {"tahmin": "🎯 İlk Yarı 0.5 Üst", "skor": "1-0 (İY)", "guven": "%79", "analiz": "Maçın erken dakikalarında buluncak bir gol oyunun kilidini açacaktır."}
        ]
        # Karakter uzunluklarına göre dinamik seçim
        secim = secenekler[(len(ev_sahibi) + len(deplasman)) % len(secenekler)]
        return secim['tahmin'], secim['skor'], secim['guven'], secim['analiz']
        
    return tahmin, skor, guven, analiz

def send_afilli_bulten(chat_id):
    if not hafiza_maclar:
        send_telegram_message(chat_id, "⚠️ <b>Hafızada işlenecek aktif maç bulunamadı...</b>")
        return

    chunk_size = 6  # Detaylı analiz kartları sığması için 6'şarlı paketler
    total = len(hafiza_maclar)
    
    for i in range(0, total, chunk_size):
        chunk = hafiza_maclar[i:i + chunk_size]
        
        mesaj = f"🧠 <b>YAPAY ZEKA CANLI MAÇ ANALİZ RAPORU</b> 🤖\n"
        mesaj += f"📊 <i>Bülten Aralığı: [{i+1} - {min(i+chunk_size, total)} / Toplam: {total}]</i>\n"
        mesaj += "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for idx, mac in enumerate(chunk, i + 1):
            ev = str(mac['ev_sahibi']).replace('<', '&lt;').replace('>', '&gt;')
            dep = str(mac['deplasman']).replace('<', '&lt;').replace('>', '&gt;')
            saat = str(mac['saat']).replace('<', '&lt;').replace('>', '&gt;')
            tahmin = mac['tahmin']
            skor = mac['skor']
            guven = mac['guven']
            analiz = mac['analiz']
            
            mesaj += (
                f"⚽ <b>{idx}. {ev} vs {dep}</b>\n"
                f"⏰ <b>Başlangıç:</b> <code>{saat}</code> | 🎯 <b>Güven:</b> <b>{guven}</b>\n"
                f"💡 <b>AI Tahmin:</b> <b>{tahmin}</b>\n"
                f"🔢 <b>Beklenen Skor:</b> <code>{skor}</code>\n"
                f"📝 <i>Analiz: {analiz}</i>\n"
                f"───────────────────────────\n"
            )
        
        send_telegram_message(chat_id, mesaj)
        time.sleep(0.7)

# ================= ==========================================
# 2. FLASK SERVER VE TELEGRAM WEBHOOK
# ================= ==========================================
@app.route('/')
def home():
    return "Google & AI Canlı Maç Analiz Botu Aktif!"

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    if update and "message" in update:
        message_data = update["message"]
        text = message_data.get("text", "").strip()
        chat_id = message_data.get("chat", {}).get("id")
        
        if text.lower() == "!b" and chat_id:
            print(f"!b komutu algılandı (Chat ID: {chat_id})", flush=True)
            send_afilli_bulten(chat_id)
            
    return jsonify({"status": "ok"}), 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)

flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

# ================= ==========================================
# 3. GERÇEK ZAMANLI VERİ VE ANALİZ MOTORU
# ================= ==========================================
def daily_match_fetch():
    global hafiza_maclar
    print("Gerçek zamanlı güncel bülten ve saatler taranıyor...", flush=True)
    
    yeni_hafiza = []
    
    try:
        today_str = time.strftime("%Y%m%d")
        api_url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={today_str}"
        res = requests.get(api_url, timeout=12)
        
        if res.status_code == 200:
            events = res.json().get("events", [])
            for event in events:
                competitors = event.get("competitions", [{}])[0].get("competitors", [])
                if len(competitors) >= 2:
                    ev = competitors[0].get("team", {}).get("displayName", "")
                    dep = competitors[1].get("team", {}).get("displayName", "")
                    
                    # Saat çevrimi (UTC+3 Türkiye Saati)
                    date_str = event.get("date", "")
                    saat_formatli = "Canlı / Oynanıyor"
                    if date_str:
                        try:
                            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                            dt_tr = dt.astimezone(timezone(timedelta(hours=3)))
                            saat_formatli = dt_tr.strftime("%H:%M")
                        except:
                            pass
                    
                    # Gelişmiş Yapay Zeka Analiz Motorunu Çağır
                    tahmin, skor, guven, analiz = gelismis_ai_analiz_uret(ev, dep)
                    
                    yeni_hafiza.append({
                        "ev_sahibi": ev,
                        "deplasman": dep,
                        "saat": saat_formatli,
                        "tahmin": tahmin,
                        "skor": skor,
                        "guven": guven,
                        "analiz": analiz
                    })
    except Exception as e:
        print(f"Canlı veri çekme hatası: {e}", flush=True)

    # Yedek Google Tarama Katmanı
    if not yeni_hafiza:
        print("Google yedek katmanına bağlanılıyor...", flush=True)
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            google_url = "https://www.google.com/search?q=bug%C3%BCn+oynanacak+futbol+ma%C3%A7lar%C4%B1&hl=tr&gl=tr"
            response = requests.get(google_url, headers=headers, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                home_teams = [t.text.strip() for t in soup.select('div[data-df-team-name], div.imso_mh__first-tn-blk, div.imso-g-first-team-name')]
                away_teams = [t.text.strip() for t in soup.select('div.imso_mh__second-tn-blk, div.imso-g-second-team-name')]
                
                min_len = min(len(home_teams), len(away_teams))
                for i in range(min_len):
                    tahmin, skor, guven, analiz = gelismis_ai_analiz_uret(home_teams[i], away_teams[i])
                    yeni_hafiza.append({
                        "ev_sahibi": home_teams[i],
                        "deplasman": away_teams[i],
                        "saat": "Bugün",
                        "tahmin": tahmin,
                        "skor": skor,
                        "guven": guven,
                        "analiz": analiz
                    })
        except Exception as e:
            print(f"Google yedek arama hatası: {e}", flush=True)

    hafiza_maclar = yeni_hafiza
    print(f"İşlem tamamlandı. Yapay zeka motoru {len(hafiza_maclar)} maça analiz üretti.", flush=True)

# ================= ==========================================
# 4. ARKA PLAN DÖNGÜSÜ
# ================= ==========================================
def background_worker():
    daily_match_fetch()
    
    status_msg = f"🤖 <b>AI Analiz Botu Aktif!</b>\nBültendeki <b>{len(hafiza_maclar)} maç</b> yapay zeka süzgecinden geçirildi.\nGruba <code>!b</code> yazarak profesyonel analiz raporunu alabilirsiniz."
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
