import os
import time
import requests
import threading
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify, send_file
from bs4 import BeautifulSoup

app = Flask(__name__)

# ================= ==========================================
# 1. TELEGRAM VE HAFIZA AYARLARI
# ================= ==========================================
TELEGRAM_BOT_TOKEN = "8894398415:AAEY_ffz8iPL8qZ8vJq3bgat7cibeQFhvI8"
TELEGRAM_CHAT_ID = "-1003991937105"

hafiza_maclar = []
canli_takip_hafizasi = {}  # Maçların anlık skor ve durumlarını takip etmek için
DOSYA_ADI = "gunluk_futbol_analiz_bulteni.txt"

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

def send_telegram_document(chat_id, file_path, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    try:
        with open(file_path, 'rb') as f:
            files = {'document': f}
            data = {'chat_id': chat_id, 'caption': caption, 'parse_mode': 'HTML'}
            response = requests.post(url, data=data, files=files, timeout=20)
            return response.json()
    except Exception as e:
        print(f"Dosya gönderme hatası: {e}", flush=True)
        return None

def gelismis_ai_analiz_uret(ev_sahibi, deplasman):
    ev_lower = ev_sahibi.lower()
    dep_lower = deplasman.lower()
    
    devler = ["real madrid", "barcelona", "manchester city", "bayern", "psg", "galatasaray", "fenerbahçe", "beşiktaş", "liverpool", "arsenal", "inter", "milan", "juventus"]
    
    ev_guclu = any(dev in ev_lower for dev in devler)
    dep_guclu = any(dev in dep_lower for dev in devler)
    
    if ev_guclu and dep_guclu:
        tahmin = "Karşılıklı Gol Var & 2.5 Üst (Zirve Mücadelesi)"
        skor = "2-1 / 2-2"
        guven = "%84 (Yüksek)"
        analiz = "İki formlu dev ekip de sahaya galibiyet için çıkacaktır. Tempomuz yüksek ve gol beklentisi (xG) üst düzeyde."
    elif ev_guclu and not dep_guclu:
        tahmin = "Ev Sahibi Net Favori (MS 1 & 1.5 Üst)"
        skor = "2-0 / 3-0"
        guven = "%89 (Çok Güçlü)"
        analiz = "Ev sahibinin iç saha baskısı ve kadro kalitesi maçın kontrolünü ilk dakikadan itibaren eline alacağını gösteriyor."
    elif not ev_guclu and dep_guclu:
        tahmin = "Deplasman Baskın Çıkar (MS 2 veya KG Var)"
        skor = "1-2 / 0-2"
        guven = "%81 (Güçlü)"
        analiz = "Deplasman ekibi kadro üstünlüğüyle oyunu domine etmeye çalışacaktır. Gollü geçmeye aday bir müsabaka."
    else:
        secenekler = [
            {"tahmin": "2.5 Alt (Taktiksel Kilitlenme)", "skor": "1-0 / 0-1", "guven": "%74", "analiz": "Orta saha mücadelesi şeklinde geçmesi beklenen, az pozisyonlu maç senaryosu."},
            {"tahmin": "Karşılıklı Gol (KG) Var", "skor": "1-1 / 2-1", "guven": "%77", "analiz": "Savunma zaafları bulunan iki ekibin de skor üretme ihtimali oldukça yüksek."},
            {"tahmin": "İlk Yarı 0.5 Üst", "skor": "1-0 (İY)", "guven": "%79", "analiz": "Maçın erken dakikalarında buluncak bir gol oyunun kilidini açacaktır."}
        ]
        secim = secenekler[(len(ev_sahibi) + len(deplasman)) % len(secenekler)]
        return secim['tahmin'], secim['skor'], secim['guven'], secim['analiz']
        
    return tahmin, skor, guven, analiz

def bulteni_not_defterine_kaydet():
    global hafiza_maclar
    tarih_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    
    with open(DOSYA_ADI, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write(f"  YAPAY ZEKA FUTBOL MAÇ & ANALİZ BÜLTENİ\n")
        f.write(f"  Oluşturulma Tarihi: {tarih_str}\n")
        f.write(f"  Toplam Maç Sayısı: {len(hafiza_maclar)}\n")
        f.write("=" * 60 + "\n\n")
        
        if not hafiza_maclar:
            f.write("Şu anda sistemde aktif maç bulunmuyor.\n")
        else:
            for idx, mac in enumerate(hafiza_maclar, 1):
                f.write(f"[{idx}] {mac['ev_sahibi']} vs {mac['deplasman']}\n")
                f.write(f"    - Başlangıç Saati : {mac['saat']}\n")
                f.write(f"    - Yapay Zeka Tahmini : {mac['tahmin']}\n")
                f.write(f"    - Beklenen Skor      : {mac['skor']}\n")
                f.write(f"    - Güven Oranı        : {mac['guven']}\n")
                f.write(f"    - Detaylı Analiz     : {mac['analiz']}\n")
                f.write("-" * 60 + "\n")

def bulten_dosyasini_gonder(chat_id):
    if not hafiza_maclar:
        send_telegram_message(chat_id, "⚠️ <b>Not defterine yazılacak aktif maç bulunamadı...</b>")
        return
    
    bulteni_not_defterine_kaydet()
    caption = f"📄 <b>Günlük Yapay Zeka Futbol Analiz Bülteni</b>\n📅 Tarih: {datetime.now().strftime('%d.%m.%Y')}\n🤖 Tüm maçlar ve detaylı analizler not defteri formatında hazırdır."
    send_telegram_document(chat_id, DOSYA_ADI, caption)

# ================= ==========================================
# 2. FLASK SERVER VE TELEGRAM WEBHOOK
# ================= ==========================================
@app.route('/')
def home():
    return "Not Defteri & Gelişmiş Canlı Takip Botu Aktif!"

@app.route('/download', methods=['GET'])
def download_file():
    if os.path.exists(DOSYA_ADI):
        return send_file(DOSYA_ADI, as_attachment=True)
    return "Henüz oluşturulmuş bir bülten dosyası yok.", 404

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    if update and "message" in update:
        message_data = update["message"]
        text = message_data.get("text", "").strip()
        chat_id = message_data.get("chat", {}).get("id")
        
        if text.lower() == "!b" and chat_id:
            print(f"!b komutu algılandı (Chat ID: {chat_id})", flush=True)
            bulten_dosyasini_gonder(chat_id)
            
    return jsonify({"status": "ok"}), 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)

flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

# ================= ==========================================
# 3. VERİ ÇEKME VE CANLI MAÇ TAKİP MOTORU
# ================= ==========================================
def daily_match_fetch():
    global hafiza_maclar
    print("Güncel bülten taranıyor...", flush=True)
    
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
                    
                    date_str = event.get("date", "")
                    saat_formatli = "Canlı / Oynanıyor"
                    if date_str:
                        try:
                            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                            dt_tr = dt.astimezone(timezone(timedelta(hours=3)))
                            saat_formatli = dt_tr.strftime("%H:%M")
                        except:
                            pass
                    
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
        print(f"Veri çekme hatası: {e}", flush=True)

    hafiza_maclar = yeni_hafiza
    bulteni_not_defterine_kaydet()
    print(f"Bülten güncellendi. {len(hafiza_maclar)} maç hafızaya alındı.", flush=True)

def live_match_monitor():
    global canli_takip_hafizasi
    print("Canlı maç takip ve detaylı gol bildirim servisi başlatıldı.", flush=True)
    
    while True:
        try:
            today_str = time.strftime("%Y%m%d")
            api_url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={today_str}"
            res = requests.get(api_url, timeout=10)
            
            if res.status_code == 200:
                events = res.json().get("events", [])
                for event in events:
                    match_id = event.get("id")
                    status_type = event.get("status", {}).get("type", {}).get("name", "")
                    status_detail = event.get("status", {}).get("type", {}).get("shortDetail", "")
                    
                    competitors = event.get("competitions", [{}])[0].get("competitors", [])
                    if len(competitors) >= 2:
                        ev = competitors[0].get("team", {}).get("displayName", "")
                        dep = competitors[1].get("team", {}).get("displayName", "")
                        
                        score_ev = int(competitors[0].get("score", 0))
                        score_dep = int(competitors[1].get("score", 0))
                        
                        if match_id not in canli_takip_hafizasi:
                            canli_takip_hafizasi[match_id] = {
                                "ev": ev, "dep": dep,
                                "score_ev": score_ev, "score_dep": score_dep,
                                "status": status_type
                            }
                        else:
                            eski = canli_takip_hafizasi[match_id]
                            
                            # Gol bildirimi kontrolü ve hangi takımın attığının tespiti
                            if (score_ev != eski["score_ev"] or score_dep != eski["score_dep"]) and status_type == "STATUS_IN_PROGRESS":
                                atan_takim = ev if score_ev > eski["score_ev"] else dep
                                
                                gol_mesaj = (
                                    f"⚽ <b>GOL!</b> ⚽\n"
                                    f"🎯 <b>Atan Takım:</b> {atan_takim}\n"
                                    f"📊 <b>Skor:</b> {ev} <b>{score_ev} - {score_dep}</b> {dep}\n"
                                    f"⏱ <b>Dakika:</b> <code>{status_detail}</code>"
                                )
                                send_telegram_message(TELEGRAM_CHAT_ID, gol_mesaj)
                                canli_takip_hafizasi[match_id]["score_ev"] = score_ev
                                canli_takip_hafizasi[match_id]["score_dep"] = score_dep
                            
                            # Maç bitti bildirimi kontrolü
                            if status_type == "STATUS_FINAL" and eski["status"] != "STATUS_FINAL":
                                bitis_mesaj = (
                                    f"🏁 <b>MAÇ SONUCU</b> 🏁\n"
                                    f"📊 <b>Final Skor:</b> {ev} <b>{score_ev} - {score_dep}</b> {dep}\n"
                                    f"🏆 <i>Karşılaşma sona erdi.</i>"
                                )
                                send_telegram_message(TELEGRAM_CHAT_ID, bitis_mesaj)
                                canli_takip_hafizasi[match_id]["status"] = "STATUS_FINAL"
        except Exception as e:
            print(f"Canlı takip döngüsü hatası: {e}", flush=True)
            
        time.sleep(120)  # Her 2 dakikada bir kontrol et

# ================= ==========================================
# 4. ARKA PLAN DÖNGÜLERİ
# ================= ==========================================
def background_worker():
    daily_match_fetch()
    
    status_msg = f"🤖 <b>AI Bülten & Canlı Takip Botu Aktif!</b>\nBültendeki <b>{len(hafiza_maclar)} maç</b> not defterine kaydedildi.\nGruba <code>!b</code> yazarak bülten dosyasını alabilirsin. Goller (atan takım ve dakika ile birlikte) ve maç sonuçları anlık olarak bildirilecektir."
    send_telegram_message(TELEGRAM_CHAT_ID, status_msg)
    
    threading.Thread(target=live_match_monitor, daemon=True).start()
    
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
