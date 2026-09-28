import os
import time
import requests
import threading
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)

# ================= ==========================================
# 1. TELEGRAM VE HAFIZA AYARLARI
# ================= ==========================================
TELEGRAM_BOT_TOKEN = "8894398415:AAEY_ffz8iPL8qZ8vJq3bgat7cibeQFhvI8"
TELEGRAM_CHAT_ID = "-1003991937105"

hafiza_maclar = []
canli_takip_hafizasi = {}

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

# ================= ==========================================
# 2. MODÜL A: NORMAL BÜLTEN & ORAN SİSTEMİ (!b) - METİN FORMATI
# ================= ==========================================
def iddaa_analiz_ve_oran_uret(ev_sahibi, deplasman, index):
    ev_lower = ev_sahibi.lower()
    dep_lower = deplasman.lower()
    
    devler = ["real madrid", "barcelona", "manchester city", "bayern", "psg", "galatasaray", "fenerbahçe", "beşiktaş", "liverpool", "arsenal", "inter", "milan", "juventus"]
    
    ev_guclu = any(dev in ev_lower for dev in devler)
    dep_guclu = any(dev in dep_lower for dev in dep_lower)
    
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

def bulten_metnini_gonder(chat_id):
    global hafiza_maclar
    if not hafiza_maclar:
        send_telegram_message(chat_id, "⚠️ <b>Bültende aktif maç bulunamadı.</b>")
        return
        
    tarih_str = datetime.now().strftime("%d.%m.%Y")
    send_telegram_message(chat_id, f"⚽ <b>RESMİ İDDAA BÜLTENİ</b>\n📅 <i>Tarih: {tarih_str}</i>")
    
    ligler = {}
    for m in hafiza_maclar:
        ligler.setdefault(m['lig'], []).append(m)
        
    for lig, mac_listesi in sorted(ligler.items()):
        lig_mesaj = f"🏆 <b>{lig.upper()}</b>\n"
        for mac in sorted(mac_listesi, key=lambda x: x['saat']):
            lig_mesaj += (
                f"<blockquote>"
                f"<code>Kod: {mac['kod']}</code> | ⏰ <b>Saat: {mac['saat']}</b>\n"
                f"📌 <b>{mac['ev_sahibi']} - {mac['deplasman']}</b>\n"
                f"📊 <i>Oranlar:</i> MS 1: <code>{mac['oran_1']}</code> | MS 0: <code>{mac['oran_0']}</code> | MS 2: <code>{mac['oran_2']}</code>\n"
                f"🎯 <b>Tahmin:</b> <i>{mac['tahmin']}</i>\n"
                f"💡 <b>Yorum:</b> {mac['yorum']}"
                f"</blockquote>\n"
            )
        send_telegram_message(chat_id, lig_mesaj)
        time.sleep(0.3)

# ================= ==========================================
# 3. MODÜL B: T2 CANLI ANALİZ SİSTEMİ (!t2) - METİN FORMATI
# ================= ==========================================
def canli_mac_analiz_uret(ev_sahibi, deplasman, skor_ev, skor_dep, dakika_str):
    toplam_gol = skor_ev + skor_dep
    try:
        dakika = int(''.join(filter(str.isdigit, dakika_str)))
    except:
        dakika = 45

    if toplam_gol >= 3:
        tahmin = "4.5 Üst & Karşılıklı Gol Var"
        yorum = f"Dakika {dakika}: Müthiş bir gol düellosu yaşanıyor, goller devam eder."
    elif toplam_gol == 0 and dakika > 60:
        tahmin = "Tek Gol & Sonradan Açılır"
        yorum = f"Dakika {dakika}: Baskı arttı, ilk golü atan maçı koparır."
    elif skor_ev != skor_dep:
        tahmin = "Favori Baskıda / 1.5 Üst"
        yorum = f"Dakika {dakika}: Geride olan takım risk alıyor, açık alanlar doğuyor."
    else:
        tahmin = "Sıradaki Golü Atan Kazanır"
        yorum = f"Dakika {dakika}: Skor dengede, takımlar kontrollü oynuyor."
        
    return tahmin, yorum

def t2_canli_analiz_gonder(chat_id):
    send_telegram_message(chat_id, "🔴 <b>T2 Bot: Canlı maçlar taranıyor ve anlık analiz yapılıyor...</b>")
    try:
        today_str = time.strftime("%Y%m%d")
        api_url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={today_str}"
        res = requests.get(api_url, timeout=12)
        
        canli_maclar = []
        if res.status_code == 200:
            events = res.json().get("events", [])
            for event in events:
                status_type = event.get("status", {}).get("type", {}).get("name", "")
                if status_type == "STATUS_IN_PROGRESS":
                    status_detail = event.get("status", {}).get("type", {}).get("shortDetail", "Devam Ediyor")
                    competitors = event.get("competitions", [{}])[0].get("competitors", [])
                    if len(competitors) >= 2:
                        ev = competitors[0].get("team", {}).get("displayName", "")
                        dep = competitors[1].get("team", {}).get("displayName", "")
                        score_ev = int(competitors[0].get("score", 0))
                        score_dep = int(competitors[1].get("score", 0))
                        
                        tahmin, yorum = canli_mac_analiz_uret(ev, dep, score_ev, score_dep, status_detail)
                        
                        canli_maclar.append({
                            "ev_sahibi": ev, "deplasman": dep,
                            "skor_ev": score_ev, "skor_dep": score_dep,
                            "dakika": status_detail, "tahmin": tahmin, "yorum": yorum
                        })
        
        if not canli_maclar:
            send_telegram_message(chat_id, "🔴 <b>T2 Canlı Analiz:</b> Şu anda oynanan canlı maç bulunmuyor.")
            return
            
        mesaj = "🔴 <b>T2 CANLI MAÇLAR & ANLIK ANALİZLER</b>\n\n"
        for mac in canli_maclar:
            mesaj += (
                f"<blockquote>"
                f"⏱ <b>Dakika:</b> <code>{mac['dakika']}</code>\n"
                f"📌 <b>{mac['ev_sahibi']}</b> <b>{mac['skor_ev']} - {mac['skor_dep']}</b> <b>{mac['deplasman']}</b>\n"
                f"⚡ <b>Canlı Tahmin:</b> <i>{mac['tahmin']}</i>\n"
                f"💡 <b>Yorum:</b> {mac['yorum']}"
                f"</blockquote>\n"
            )
        send_telegram_message(chat_id, mesaj)
            
    except Exception as e:
        print(f"T2 Canlı analiz hatası: {e}", flush=True)
        send_telegram_message(chat_id, "⚠️ T2 Canlı maçlar taranırken bir hata oluştu.")

# ================= ==========================================
# 4. FLASK WEBHOOK VE YÖNLENDİRİCİ
# ================= ==========================================
@app.route('/')
def home():
    return "Metin Tabanlı İddaa & T2 Canlı Bot Aktif!"

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    if update and "message" in update:
        message_data = update["message"]
        text = message_data.get("text", "").strip().lower()
        chat_id = message_data.get("chat", {}).get("id")
        
        if text == "!b" and chat_id:
            print(f"!b komutu algılandı (Chat ID: {chat_id})", flush=True)
            bulten_metnini_gonder(chat_id)
        elif text == "!t2" and chat_id:
            print(f"T2 Modülü: !t2 komutu algılandı (Chat ID: {chat_id})", flush=True)
            t2_canli_analiz_gonder(chat_id)
            
    return jsonify({"status": "ok"}), 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)

flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

# ================= ==========================================
# 5. ARKA PLAN DÖNGÜLERİ
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
                        "lig": league_name, "kod": mac_kodu, "ev_sahibi": ev, "deplasman": dep,
                        "saat": saat_formatli, "oran_1": o1, "oran_0": o0, "oran_2": o2,
                        "tahmin": tahmin, "yorum": yorum
                    })
    except Exception as e:
        print(f"Veri çekme hatası: {e}", flush=True)

    hafiza_maclar = yeni_hafiza
    print(f"Bülten güncellendi. Toplam {len(hafiza_maclar)} maç hafızaya alındı.", flush=True)

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
                                "ev": ev, "dep": dep, "score_ev": score_ev, "score_dep": score_dep, "status": status_type
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

def background_worker():
    daily_match_fetch()
    
    status_msg = (
        f"🤖 <b>Metin Tabanlı İddaa & T2 Canlı Bot Aktif!</b>\n\n"
        f"📌 <b>Komutlar:</b>\n"
        f"👉 <code>!b</code> -> Günlük bülten ve oranlar (Metin/Alıntı)\n"
        f"👉 <code>!t2</code> -> Canlı maçlar ve anlık analizler (Metin/Alıntı)"
    )
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
