import os
import time
import requests
import threading
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify
from groq import Groq

app = Flask(__name__)

# ================= ==========================================
# 1. AYARLAR VE GROQ BAĞLANTISI
# ================= ==========================================
TELEGRAM_BOT_TOKEN = "8894398415:AAEY_ffz8iPL8qZ8vJq3bgat7cibeQFhvI8"
TELEGRAM_CHAT_ID = "-1003991937105"

# Groq İstemcisi (Render'da GROQ_API_KEY olmalı)
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

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
# 2. LİG VE TAKIM ÇEVİRİLERİ
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

def toplu_grok_analiz_uret(mac_listesi_text):
    """Tüm maç listesini tek seferde Groq'a gönderip şık formatta tahmin alır"""
    prompt = (
        f"Sen profesyonel bir futbol analiz uzmanı ve iddaa yorumorusun. "
        f"Aşağıda bugün oynanacak olan maçların bir listesi var. Her biri için kısa birer iddaa tahmini, oranı ve yorumu üret.\n\n"
        f"Maç Listesi:\n{mac_listesi_text}\n\n"
        f"Lütfen her maç için Kesinlikle şu formatı satır satır bozmadan kullan:\n"
        f"KOD:[Maç Kodu] | ORAN:[MS1 - MS0 - MS2] | TAHMİN:[...] | YORUM:[...]\n"
        f"Başka hiçbir ekstra açıklama ekleme, sadece yukarıdaki formatta her maç için bir satır yaz."
    )
    try:
        completion = groq_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": "Sen uzman bir futbol analistisin ve kesinlikle istenen formatın dışına çıkmazsın."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2500
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"Groq Toplu API hata: {e}", flush=True)
        return ""

def bulten_metnini_gonder(chat_id):
    global hafiza_maclar
    if not hafiza_maclar:
        send_telegram_message(chat_id, "⚠️ <b>Futbol bülteninde aktif maç bulunamadı.</b>")
        return
        
    simdi_tr = datetime.now(timezone(timedelta(hours=3)))
    tarih_str = format_turkce_tarih(simdi_tr)
    send_telegram_message(chat_id, f"⚽ <b>GROQ TOPLU ANALİZLİ BÜLTEN</b>\n📅 <i>Tarih: {tarih_str}</i>")
    
    mac_metinleri = ""
    mac_dict = {}
    for m in hafiza_maclar:
        mac_metinleri += f"Kod: {m['kod']} | Lig: {m['lig']} | Saat: {m['saat']} | Maç: {m['ev_sahibi']} vs {m['deplasman']}\n"
        mac_dict[m['kod']] = m
    
    toplu_sonuc = toplu_grok_analiz_uret(mac_metinleri)
    
    # Gelen ham yanıtı parçalayıp şık kartlar haline getirelim
    cikti_metni = ""
    satirlar = toplu_sonuc.split('\n')
    
    for satir in satirlar:
        if "KOD:" in satir:
            try:
                # Örn: KOD:501 | ORAN:[2.20 - 3.30 - 3.00] | TAHMİN:X | YORUM:Y
                parcalar = satir.split('|')
                kod_parca = [p for p in parcalar if "KOD:" in p][0]
                oran_parca = [p for p in parcalar if "ORAN:" in p][0]
                tahmin_parca = [p for p in parcalar if "TAHMİN:" in p][0]
                yorum_parca = [p for p in parcalar if "YORUM:" in p][0]
                
                kod = kod_parca.split(':')[1].strip().replace(']', '').strip()
                oranlar = oran_parca.split(':')[1].strip().replace('[', '').replace(']', '').strip()
                tahmin = tahmin_parca.split(':')[1].strip().replace(']', '').strip()
                yorum = yorum_parca.split(':')[1].strip().replace(']', '').strip()
                
                if kod in mac_dict:
                    m_bilgi = mac_dict[kod]
                    # Şık Kart Formatı
                    kart = (
                        f"🏆 <b>{m_bilgi['lig']}</b>\n"
                        f"⏰ <b>Saat:</b> {m_bilgi['saat']} | 🔑 <b>Kod:</b> <code>{m_bilgi['kod']}</code>\n"
                        f"⚔️ <b>{m_bilgi['ev_sahibi']} vs {m_bilgi['deplasman']}</b>\n"
                        f"📊 <b>Oranlar:</b> <code>{oranlar}</code>\n"
                        f"🎯 <b>Tahmin:</b> <b>{tahmin}</b>\n"
                        f"💡 <i>Yorum: {yorum}</i>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    )
                    
                    if len(cikti_metni + kart) > 3900:
                        send_telegram_message(chat_id, f"<blockquote>{cikti_metni}</blockquote>")
                        cikti_metni = kart
                        time.sleep(0.3)
                    else:
                        cikti_metni += kart
            except Exception as ex:
                print(f"Satır ayrıştırma hatası: {ex} -> Satır: {satir}", flush=True)
                continue

    if cikti_metni:
        send_telegram_message(chat_id, f"<blockquote>{cikti_metni}</blockquote>")
    elif toplu_sonuc:
        # Eğer özel format tutmazsa ham metni doğrudan blok olarak basar
        send_telegram_message(chat_id, f"<blockquote>{toplu_sonuc}</blockquote>")

# ================= ==========================================
# 3. MODÜL B: T2 CANLI YAPAY ZEKA ANALİZİ (!t2)
# ================= ==========================================
def t2_canli_analiz_gonder(chat_id):
    send_telegram_message(chat_id, "🔴 <b>Groq T2: Oynanan futbol maçları taranıyor ve yapay zeka canlı analiz yapıyor...</b>")
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
                        
                        canli_maclar.append(f"{ev} {score_ev} - {score_dep} {dep} (Dakika: {status_detail})")
        
        if not canli_maclar:
            send_telegram_message(chat_id, "🔴 <b>Groq Canlı Analiz:</b> Şu anda oynanan canlı futbol maçı bulunmuyor.")
            return
            
        canli_text = "\n".join(canli_maclar)
        prompt = f"Şu an oynanan canlı futbol maçları:\n{canli_text}\nBu maçların gidişatına göre kısa birer canlı iddaa yorumu yap."
        
        try:
            completion = groq_client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000
            )
            yorumlar = completion.choices[0].message.content.strip()
        except:
            yorumlar = "Canlı analiz şu an üretilemedi."

        send_telegram_message(chat_id, f"🔴 <b>GROK CANLI MAÇ YORUMLARI</b>\n\n<blockquote>{yorumlar}</blockquote>")
            
    except Exception as e:
        print(f"Canlı analiz hata: {e}", flush=True)
        send_telegram_message(chat_id, "⚠️ Canlı analiz yapılırken bir hata oluştu.")

# ================= ==========================================
# 4. FLASK WEBHOOK VE YÖNLENDİRİCİ
# ================= ==========================================
@app.route('/')
def home():
    return "Groq Toplu Analiz Futbol Botu Aktif!"

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
# 5. ARKA PLAN DÖNGÜLERİ
# ================= ==========================================
def daily_match_fetch():
    global hafiza_maclar
    print("Futbol bülteni taranıyor...", flush=True)
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
                    
                    yeni_hafiza.append({
                        "lig": league_name, "kod": mac_kodu, "ev_sahibi": ev, "deplasman": dep, "saat": saat_formatli
                    })
    except Exception as e:
        print(f"Futbol veri çekme hatası: {e}", flush=True)

    hafiza_maclar = yeni_hafiza
    print(f"Bülten güncellendi. Toplam {len(hafiza_maclar)} futbol maçı hafızaya alındı.", flush=True)

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
        f"🤖 <b>Groq Toplu Analiz Futbol Botu Aktif!</b>\n\n"
        f"📅 <b>Bugün:</b> {tarih_str}\n\n"
        f"📌 <b>Komutlar:</b>\n"
        f"👉 <code>!b</code> -> Toplu Groq Tahminli Bülten\n"
        f"👉 <code>!t2</code> -> Canlı Toplu Maç Yorumları"
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
