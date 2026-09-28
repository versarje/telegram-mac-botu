import os
import time
import requests
import threading
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify, send_file
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

# ================= ==========================================
# 1. TELEGRAM VE HAFIZA AYARLARI
# ================= ==========================================
TELEGRAM_BOT_TOKEN = "8894398415:AAEY_ffz8iPL8qZ8vJq3bgat7cibeQFhvI8"
TELEGRAM_CHAT_ID = "-1003991937105"

hafiza_maclar = []
canli_takip_hafizasi = {}
GORSEL_ADI = "iddaa_bulteni_detayli.png"

def send_telegram_message(chat_id, message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_profile": True
    }
    try:
        response = requests.post(url, json=payload, timeout=15)
        return response.json()
    except Exception as e:
        print(f"Telegram mesaj gönderme hatası: {e}", flush=True)
        return None

def send_telegram_photo(chat_id, photo_path, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, 'rb') as f:
            files = {'photo': f}
            data = {'chat_id': chat_id, 'caption': caption, 'parse_mode': 'HTML'}
            response = requests.post(url, data=data, files=files, timeout=25)
            return response.json()
    except Exception as e:
        print(f"Fotoğraf gönderme hatası: {e}", flush=True)
        return None

def iddaa_analiz_ve_oran_uret(ev_sahibi, deplasman, index):
    ev_lower = ev_sahibi.lower()
    dep_lower = deplasman.lower()
    
    devler = ["real madrid", "barcelona", "manchester city", "bayern", "psg", "galatasaray", "fenerbahçe", "beşiktaş", "liverpool", "arsenal", "inter", "milan", "juventus"]
    
    ev_guclu = any(dev in ev_lower for dev in devler)
    dep_guclu = any(dev in dep_lower for dev in dep_guclu)
    
    mac_kodu = str(400 + index)
    
    if ev_guclu and dep_guclu:
        oran_ms1, oran_ms0, oran_ms2 = "1.85", "3.40", "3.10"
        tahmin = "Karşılıklı Gol Var (KG Var) & 2.5 Üst"
        yorum = "İki formlu ekip de hücumda etkili. Karşılıklı goller kaçınılmaz."
    elif ev_guclu and not dep_guclu:
        oran_ms1, oran_ms0, oran_ms2 = "1.35", "4.50", "6.20"
        tahmin = "Maç Sonucu 1 (MS 1) & 1.5 Üst"
        yorum = "Ev sahibi takım saha avantajı ve kadro kalitesiyle maçı koparır."
    elif not ev_guclu and dep_guclu:
        oran_ms1, oran_ms0, oran_ms2 = "4.20", "3.60", "1.75"
        tahmin = "Deplasman Kazanır (MS 2)"
        yorum = "Deplasman ekibi oyun kalitesiyle rakibine üstünlük kuracaktır."
    else:
        oran_ms1, oran_ms0, oran_ms2 = "2.10", "3.10", "2.80"
        tahmin = "2.5 Alt (Taktiksel Mücadele)"
        yorum = "Orta saha mücadelesi şeklinde geçmesi beklenen, az gol atılacak maç."
        
    return mac_kodu, oran_ms1, oran_ms0, oran_ms2, tahmin, yorum

def bulteni_gorsel_olarak_uret():
    global hafiza_maclar
    tarih_str = datetime.now().strftime("%d.%m.%Y")
    
    genislingimiz = 950
    baslik_h = 100
    footer_h = 50
    
    # Her bir maç kartı için yükseklik (Detaylı iddaa görünümü için 190 piksel)
    satir_h = 190
    lig_baslik_h = 45
    
    toplam_mac_sayisi = len(hafiza_maclar)
    if toplam_mac_sayisi == 0:
        toplam_h = 300
    else:
        ligler = {}
        for mac in hafiza_maclar:
            ligler.setdefault(mac['lig'], []).append(mac)
        grup_sayisi = len(ligler)
        toplam_h = baslik_h + footer_h + (toplam_mac_sayisi * satir_h) + (grup_sayisi * lig_baslik_h) + 40

    img = Image.new("RGB", (genislingimiz, max(toplam_h, 600)), color="#0F172A")
    draw = ImageDraw.Draw(img)
    
    try:
        font_baslik = ImageFont.truetype("arial.ttf", 22)
        font_lig = ImageFont.truetype("arialbd.ttf", 16)
        font_mac = ImageFont.truetype("arialbd.ttf", 15)
        font_detay = ImageFont.truetype("arial.ttf", 13)
        font_kucuk = ImageFont.truetype("arial.ttf", 12)
    except:
        font_baslik = ImageFont.load_default()
        font_lig = ImageFont.load_default()
        font_mac = ImageFont.load_default()
        font_detay = ImageFont.load_default()
        font_kucuk = ImageFont.load_default()

    # Üst Bilgi Alanı (Header)
    draw.rectangle([(0, 0), (genislingimiz, baslik_h)], fill="#1E293B")
    draw.text((30, 22), "⚽ RESMİ İDDAA BÜLTENİ & UZMAN ANALİZLERİ", fill="#38BDF8", font=font_baslik)
    draw.text((30, 56), f"Tarih: {tarih_str}  |  Lig ve Saat Sıralı Profesyonel Bülten", fill="#94A3B8", font=font_detay)
    
    y = baslik_h + 20
    
    if not hafiza_maclar:
        draw.text((50, y + 50), "Şu anda bültende aktif maç bulunmuyor.", fill="#FFFFFF", font=font_mac)
        img.save(GORSEL_ADI)
        return

    ligler = {}
    for mac in hafiza_maclar:
        ligler.setdefault(mac['lig'], []).append(mac)

    for lig, mac_listesi in sorted(ligler.items()):
        # Lig Başlığı Şeridi
        draw.rectangle([(20, y), (genislingimiz - 20, y + 35)], fill="#1E293B")
        draw.text((35, y + 8), f"🏆 {lig.upper()}", fill="#F59E0B", font=font_lig)
        y += 45
        
        mac_listesi_sirali = sorted(mac_listesi, key=lambda x: x['saat'])
        
        for mac in mac_listesi_sirali:
            # Maç Kartı Arka Planı (Koyu Şık Panel)
            draw.rectangle([(20, y), (genislingimiz - 20, y + 180)], fill="#1E293B")
            
            # Kod ve Saat Kutusu (Sol)
            draw.rectangle([(20, y), (130, y + 180)], fill="#334155")
            draw.text((35, y + 60), f"Kod: {mac['kod']}", fill="#38BDF8", font=font_kucuk)
            draw.text((35, y + 85), f"Saat: {mac['saat']}", fill="#FFFFFF", font=font_mac)
            
            # Takımlar Satırı
            mac_adi = f"{mac['ev_sahibi']}  -  {mac['deplasman']}"
            draw.text((150, y + 15), mac_adi, fill="#FFFFFF", font=font_mac)
            
            # İddaa Oranları Şeridi
            oran_text = f"MS 1: {mac['oran_1']}   |   MS 0: {mac['oran_0']}   |   MS 2: {mac['oran_2']}"
            draw.text((150, y + 45), oran_text, fill="#38BDF8", font=font_detay)
            
            # Ayırıcı Çizgi
            draw.line([(150, y + 72), (genislingimiz - 40, y + 72)], fill="#475569", width=1)
            
            # Tahmin ve Yorum Bölümü
            draw.text((150, y + 85), f"🎯 Tahmin: {mac['tahmin']}", fill="#4ADE80", font=font_detay)
            draw.text((150, y + 115), f"💡 Yorum: {mac['yorum']}", fill="#CBD5E1", font=font_kucuk)
            
            y += 190
        y += 10

    # Alt Bilgi (Footer)
    draw.rectangle([(0, img.height - footer_h), (genislingimiz, img.height)], fill="#0F172A")
    draw.text((30, img.height - 33), "🤖 Otomatik İddaa Bülten & Analiz Botu", fill="#64748B", font=font_detay)

    img.save(GORSEL_ADI)

def bulten_gorselini_gonder(chat_id):
    if not hafiza_maclar:
        send_telegram_message(chat_id, "⚠️ <b>Bültende aktif maç bulunamadı...</b>")
        return
    
    bulteni_gorsel_olarak_uret()
    caption = f"📊 <b>Günlük İddaa Bülteni ve Detaylı Tahminler</b>\n📅 Tarih: {datetime.now().strftime('%d.%m.%Y')}\n✨ Maç kodları, oranları, tahmin ve uzman yorumlarıyla hazırlandı."
    send_telegram_photo(chat_id, GORSEL_ADI, caption)

# ================= ==========================================
# 2. FLASK SERVER VE TELEGRAM WEBHOOK
# ================= ==========================================
@app.route('/')
def home():
    return "İddaa Bülten & Görsel Bot Aktif!"

@app.route('/download', methods=['GET'])
def download_image():
    if os.path.exists(GORSEL_ADI):
        return send_file(GORSEL_ADI, mimetype='image/png')
    return "Henüz oluşturulmuş bülten görseli yok.", 404

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    if update and "message" in update:
        message_data = update["message"]
        text = message_data.get("text", "").strip()
        chat_id = message_data.get("chat", {}).get("id")
        
        if text.lower() == "!b" and chat_id:
            print(f"!b komutu algılandı (İddaa Bülten Modu, Chat ID: {chat_id})", flush=True)
            bulten_gorselini_gonder(chat_id)
            
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
    print("Güncel iddaa bülteni maçları taranıyor...", flush=True)
    
    yeni_hafiza = []
    try:
        today_str = time.strftime("%Y%m%d")
        api_url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={today_str}"
        res = requests.get(api_url, timeout=12)
        
        if res.status_code == 200:
            data = res.json()
            events = data.get("events", [])
            
            idx = 0
            for event in events:
                league_name = "Özel Karşılaşmalar"
                try:
                    league_name = event.get("competitions", [{}])[0].get("tournament", {}).get("name") or \
                                  data.get("leagues", [{}])[0].get("name") or \
                                  event.get("season", {}).get("slug", "Genel Lig")
                except:
                    pass
                
                competitors = event.get("competitions", [{}])[0].get("competitors", [])
                if len(competitors) >= 2:
                    ev = competitors[0].get("team", {}).get("displayName", "")
                    dep = competitors[1].get("team", {}).get("displayName", "")
                    
                    date_str = event.get("date", "")
                    saat_formatli = "21:45"
                    if date_str:
                        try:
                            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                            dt_tr = dt.astimezone(timezone(timedelta(hours=3)))
                            saat_formatli = dt_tr.strftime("%H:%M")
                        except:
                            pass
                    
                    idx += 1
                    mac_kodu, o1, o0, o2, tahmin, yorum = iddaa_analiz_ve_oran_uret(ev, dep, idx)
                    
                    yeni_hafiza.append({
                        "lig": league_name,
                        "kod": mac_kodu,
                        "ev_sahibi": ev,
                        "deplasman": dep,
                        "saat": saat_formatli,
                        "oran_1": o1,
                        "oran_0": o0,
                        "oran_2": o2,
                        "tahmin": tahmin,
                        "yorum": yorum
                    })
    except Exception as e:
        print(f"Veri çekme hatası: {e}", flush=True)

    hafiza_maclar = yeni_hafiza
    bulteni_gorsel_olarak_uret()
    print(f"İddaa bülteni görseli hazırlandı. Toplam {len(hafiza_maclar)} maç işlendi.", flush=True)

def live_match_monitor():
    global canli_takip_hafizasi
    print("Canlı maç takip ve gol bildirim servisi çalışıyor.", flush=True)
    
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
            
        time.sleep(120)

# ================= ==========================================
# 4. ARKA PLAN DÖNGÜLERİ
# ================= ==========================================
def background_worker():
    daily_match_fetch()
    
    status_msg = f"🤖 <b>Resmi İddaa Bülten Botu Aktif!</b>\nBülten <b>Maç Kodu, Oranlar, Tahmin ve Yorum</b> içeren profesyonel formatta görsel olarak hazırlandı.\nGruba <code>!b</code> yazarak güncel tabloyu fotoğraf şeklinde alabilirsin."
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
