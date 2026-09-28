import os
import time
import requests
import threading
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify
from google import genai

app = Flask(__name__)

# ================= ==========================================
# 1. AYARLAR VE GEMINI BAĞLANTISI
# ================= ==========================================
TELEGRAM_BOT_TOKEN = "8894398415:AAEY_ffz8iPL8qZ8vJq3bgat7cibeQFhvI8"
TELEGRAM_CHAT_ID = "-1003991937105"

# Gemini İstemcisi (Ortam değişkeninden API anahtarını alır)
gemini_client = genai.Client()

hafiza_maclar = []
canli_takip_hafizasi = {}

TURKCE_GUNLER = {
    "Monday": "Pazartesi", "Tuesday": "Salı", "Wednesday": "Çarşamba",
    "Thursday": "Perşembe", "Friday": "Cuma", "Saturday": "Cumartesi", "Sunday": "Pazar"
}

def format_turkce_tarih(dt_obj):
    gun_en = dt_obj.strftime("%A")
    gun_tr = TURKCE_GUNLER.get(gun_en, gun_en)
    sayisal_tarih = dt_obj.strftime("%d/%m/%Y")
    return f"{sayisal_tarih} - {gun_tr}"

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
# 2. FUTBOL ÇEVİRİ VE GEMINI YAPAY ZEKA TAHMİN SİSTEMİ
# ================= ==========================================
LIG_CEVIRI = {
    "English Premier League": "İngiltere Premier Lig",
    "Spanish La Liga": "İspanya La Liga",
    "Italian Serie A": "İtalya Serie A",
    "German Bundesliga": "Almanya Bundesliga",
    "French Ligue 1": "Fransa Ligue 1",
    "UEFA Champions League": "UEFA Şampiyonlar Ligi",
    "UEFA Europa League": "UEFA Avrupa Ligi",
    "Turkish Süper Lig": "Türkiye Süper Lig"
}

TAKIM_CEVIRI = {
    "Real Madrid": "Real Madrid", "Barcelona": "Barcelona",
    "Manchester City": "Manchester City", "Bayern Munich": "Bayern Münih",
    "Paris Saint-Germain": "Paris Saint-Germain", "Galatasaray": "Galatasaray",
    "Fenerbahçe": "Fenerbahçe", "Beşiktaş": "Beşiktaş"
}

def cevir_isim(isim, tur="takim"):
    if tur == "lig":
        return LIG_CEVIRI.get(isim, isim)
    else:
        return TAKIM_CEVIRI.get(isim, isim)

def gemini_mac_tahmini_uret(ev_sahibi, deplasman, lig_adi):
    """Gemini yapay zekasına maç hakkında analiz ve tahmin sorar"""
    prompt = (
        f"Sen profesyonel bir futbol analiz uzmanı ve iddaa yorumorusun. "
        f"Lig: {lig_adi}, Ev Sahibi: {ev_sahibi}, Deplasman: {deplasman}. "
        f"Bu maç için kısa bir iddaa analizi yap. Şu formatta yanıt ver:\n"
        f"Oranlar (MS1, MS0, MS2 şeklinde tahmini oranlar örn: 1.70 - 3.40 - 4.10):\n"
        f"Tahmin (En olası bahis tercihi örn: MS 1 veya KG Var):\n"
        f"Yorum (2 cümlelik profesyonel analiz):\n"
        f"Lütfen aşırı uzun yazma, tam Telegram formatına uygun olsun."
    )
    try:
        response = gemini_client.models.generate_content(
            model='gemini-3.8-flash',
            contents=prompt,
        )
        metin = response.text.strip()
        return metin
    except Exception as e:
        print(f"Gemini API hata: {e}", flush=True)
        return "Oranlar: 2.10 - 3.10 - 2.80\nTahmin: 2.5 Alt\nYorum: Gemini analizi şu an yüklenemedi, standart sistem devrede."

def bulten_metnini_gonder(chat_id):
    global hafiza_maclar
    if not hafiza_maclar:
        send_telegram_message(chat_id, "⚠️ <b>Futbol bülteninde aktif maç bulunamadı.</b>")
        return
        
    simdi_tr = datetime.now(timezone(timedelta(hours=3)))
    tarih_str = format_turkce_tarih(simdi_tr)
    send_telegram_message(chat_id, f"⚽ <b>GEMİNİ DESTEKLİ FUTBOL BÜLTENİ</b>\n📅 <i>Tarih: {tarih_str}</i>")
    
    ligler = {}
    for m in hafiza_maclar:
        ligler.setdefault(m['lig'], []).append(m)
        
    for lig, mac_listesi in sorted(ligler.items()):
        lig_mesaj = f"🏆 <b>{lig.upper()}</b>\n"
        for mac in sorted(mac_listesi, key=lambda x: x['saat']):
            lig_mesaj += (
                f"<blockquote>"
                f"<code>Kod: {mac['kod']}</code> | ⏰ <b>Saat: {mac['saat']} (TR)</b>\n"
                f"📌 <b>{mac['ev_sahibi']} - {mac['deplasman']}</b>\n"
                f"🤖 <b>Gemini Analizi:</b>\n{mac['gemini_analiz']}"
                f"</blockquote>\n"
            )
        send_telegram_message(chat_id, lig_mesaj)
        time.sleep(0.4)

# ================= ==========================================
# 3. MODÜL B: T2 CANLI YAPAY ZEKA ANALİZİ (!t2)
# ================= ==========================================
def t2_canli_analiz_gonder(chat_id):
    send_telegram_message(chat_id, "🔴 <b>Gemini T2: Oynanan futbol maçları taranıyor ve yapay zeka canlı analiz yapıyor...</b>")
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
                        ev = cevir_isim(competitors[0].get("team", {}).get("displayName", ""), "takim")
                        dep = cevir_isim(competitors[1].get("team", {}).get("displayName", ""), "takim")
                        score_ev = int(competitors[0].get("score", 0))
                        score_dep = int(competitors[1].get("score", 0))
                        
                        # Canlı maç için Gemini yorumu
                        prompt = f"Futbol Canlı Maç: {ev} {score_ev} - {score_dep} {dep}, Dakika: {status_detail}. Bu canlı durum için sonraki gol veya maç sonu tahmini yap (tek cümle)."
                        try:
                            resp = gemini_client.models.generate_content(model='gemini-3.8-flash', contents=prompt)
                            canli_yorum = resp.text.strip()
                        except:
                            canli_yorum = "Mücadele tempolu devam ediyor, sonraki golü atan avantajı yakalar."
                        
                        canli_maclar.append({
                            "ev_sahibi": ev, "deplasman": dep,
                            "skor_ev": score_ev, "skor_dep": score_dep,
                            "dakika": status_detail, "yorum": canli_yorum
                        })
        
        if not canli_maclar:
            send_telegram_message(chat_id, "🔴 <b>Gemini Canlı Analiz:</b> Şu anda oynanan canlı futbol maçı bulunmuyor.")
            return
            
        mesaj = "🔴 <b>GEMİNİ CANLI MAÇ YORUMLARI</b>\n\n"
        for mac in canli_maclar:
            mesaj += (
                f"<blockquote>"
                f"⏱ <b>Dakika:</b> <code>{mac['dakika']}</code>\n"
                f"📌 <b>{mac['ev_sahibi']}</b> <b>{mac['skor_ev']} - {mac['skor_dep']}</b> <b>{mac['deplasman']}</b>\n"
                f"🤖 <b>Yapay Zeka Canlı Görüşü:</b> {mac['yorum']}"
                f"</blockquote>\n"
            )
        send_telegram_message(chat_id, mesaj)
            
    except Exception as e:
        print(f"Canlı analiz hata: {e}", flush=True)
        send_telegram_message(chat_id, "⚠️ Canlı analiz yapılırken bir hata oluştu.")

# ================= ==========================================
# 4. FLASK WEBHOOK VE YÖNLENDİRİCİ
# ================= ==========================================
@app.route('/')
def home():
    return "Gemini Destekli Futbol Botu Aktif!"

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    if update and "message" in update:
        message_data = update["message"]
        text = message_data.get("text", "").strip().lower()
        chat_id = message_data.get("chat", {}).get("id")
        
        if text == "!b" and chat_id:
            bulten_metnini_gonder(chat_id)
        elif text == "!t2" and chat_id:
            t2_canli_analiz_gonder(chat_id)
            
    return jsonify({"status": "ok"}), 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)

flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

# ================= ==========================================
# 5. ARKA PLAN DÖNGÜLERİ (Futbol Bülteni & Gol Takibi)
# ================= ==========================================
def daily_match_fetch():
    global hafiza_maclar
    print("Futbol bülteni ve Gemini analizleri hazırlanıyor...", flush=True)
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
                league_ham = "Futbol Ligi"
                try:
                    league_ham = event.get("competitions", [{}])[0].get("tournament", {}).get("name") or \
                                 data.get("leagues", [{}])[0].get("name") or \
                                 event.get("season", {}).get("slug", "Futbol Maçı")
                except:
                    pass
                
                league_name = cevir_isim(league_ham, "lig")

                competitors = event.get("competitions", [{}])[0].get("competitors", [])
                if len(competitors) >= 2:
                    ev = cevir_isim(competitors[0].get("team", {}).get("displayName", ""), "takim")
                    dep = cevir_isim(competitors[1].get("team", {}).get("displayName", ""), "takim")
                    
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
                    mac_kodu = str(500 + idx)
                    
                    # Her maç için Gemini yapay zeka analizini çağırıyoruz
                    gemini_analiz = gemini_mac_tahmini_uret(ev, dep, league_name)
                    
                    yeni_hafiza.append({
                        "lig": league_name, "kod": mac_kodu, "ev_sahibi": ev, "deplasman": dep,
                        "saat": saat_formatli, "gemini_analiz": gemini_analiz
                    })
                    # API limitlerine takılmamak için minik bekleme
                    time.sleep(0.5)
    except Exception as e:
        print(f"Futbol veri çekme hatası: {e}", flush=True)

    hafiza_maclar = yeni_hafiza
    print(f"Bülten güncellendi. Toplam {len(hafiza_maclar)} futbol maçı Gemini analizleriyle hafızaya alındı.", flush=True)

def live_match_monitor():
    global canli_takip_hafizasi
    print("Futbol canlı skor ve gol takip servisi aktif.", flush=True)
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
                        ev = cevir_isim(competitors[0].get("team", {}).get("displayName", ""), "takim")
                        dep = cevir_isim(competitors[1].get("team", {}).get("displayName", ""), "takim")
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
                                    f"⚽ <b>FUTBOL - GOL SESİ!</b> ⚽\n"
                                    f"🎯 <b>Golü Atan:</b> {atan_takim}\n"
                                    f"📊 <b>Anlık Skor:</b> {ev} <b>{score_ev} - {score_dep}</b> {dep}\n"
                                    f"⏱ <b>Dakika:</b> <code>{status_detail}</code>"
                                )
                                send_telegram_message(TELEGRAM_CHAT_ID, gol_mesaj)
                                canli_takip_hafizasi[match_id]["score_ev"] = score_ev
                                canli_takip_hafizasi[match_id]["score_dep"] = score_dep
                            
                            if status_type == "STATUS_FINAL" and eski["status"] != "STATUS_FINAL":
                                bitis_mesaj = (
                                    f"🏁 <b>MAÇ SONUCU</b> 🏁\n"
                                    f"📊 <b>Final Skor:</b> {ev} <b>{score_ev} - {score_dep}</b> {dep}"
                                )
                                send_telegram_message(TELEGRAM_CHAT_ID, bitis_mesaj)
                                canli_takip_hafizasi[match_id]["status"] = "STATUS_FINAL"
        except Exception as e:
            print(f"Canlı takip döngüsü hatası: {e}", flush=True)
        time.sleep(120)

def background_worker():
    daily_match_fetch()
    
    simdi_tr = datetime.now(timezone(timedelta(hours=3)))
    tarih_str = format_turkce_tarih(simdi_tr)
    
    status_msg = (
        f"🤖 <b>Gemini Destekli Futbol Botu Aktif!</b>\n\n"
        f"📅 <b>Bugün:</b> {tarih_str}\n\n"
        f"📌 <b>Komutlar:</b>\n"
        f"👉 <code>!b</code> -> Gemini Tahminli Futbol Bülteni\n"
        f"👉 <code>!t2</code> -> Yapay Zeka Canlı Maç Yorumları"
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
