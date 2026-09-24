import os
import math
import time
import requests
import threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# ==========================================
# ⚙️ KONFİGÜRASYONLAR
# ==========================================
API_KEY = "b699d9effa443321a65fd145ec78ede1"
BASE_URL = "https://v3.football.api-sports.io"
TELEGRAM_BOT_TOKEN = "8894398415:AAEY_ffz8iPL8qZ8vJq3bgat7cibeQFhvI8"
TELEGRAM_CHAT_ID = "-1004461429503"

HEADERS = {
    "x-apisports-key": API_KEY,
    "Accept": "application/json"
}

LIG_ID_BONUS = [39, 140, 135, 78, 61, 88, 203, 144, 94, 2, 3, 848, 5]

# Bildirilen maçların id'lerini hafızada tutarak tekrar atılmasını engelliyoruz
BILDIRILEN_MACLAR = set()

# ==========================================
# 1. YARDIMCI FONKSİYONLAR
# ==========================================
def telegram_post(metin, chat_id=None):
    target_chat = chat_id if chat_id else TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": metin,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Telegram gonderme hatasi:", e)

def poisson_gol_olasiligi(lmbda, k):
    return (math.pow(lmbda, k) * math.exp(-lmbda)) / math.factorial(k)

def tahmin_ve_oran_hesapla(lid, ust25, kg_var):
    eff_ust = ust25 if ust25 else 1.80
    eff_kg = kg_var if kg_var else 1.80

    prob_ust_implied = (1 / eff_ust) * 100
    prob_kg_implied = (1 / eff_kg) * 100
    beklenen_toplam_gol = 2.5 * (1.85 / eff_ust)

    p_ev_0 = poisson_gol_olasiligi(beklenen_toplam_gol / 2, 0)
    p_dep_0 = poisson_gol_olasiligi(beklenen_toplam_gol / 2, 0)
    p_kg_yok = p_ev_0 + p_dep_0 - (p_ev_0 * p_dep_0)
    p_kg_var_poisson = (1 - p_kg_yok) * 100
    p_ust_poisson = min((beklenen_toplam_gol / 2.5) * 55, 90)

    ai_ust_score = (p_ust_poisson * 0.6) + (prob_ust_implied * 0.4)
    ai_kg_score = (p_kg_var_poisson * 0.6) + (prob_kg_implied * 0.4)

    if lid in LIG_ID_BONUS:
        ai_ust_score += 5.0
        ai_kg_score += 4.0

    ai_ust_score = round(min(ai_ust_score, 95.0), 1)
    ai_kg_score = round(min(ai_kg_score, 95.0), 1)

    tahmin = "⚽ 2.5 ÜST POTANSİYELİ"
    if ai_ust_score >= 52.0 and ai_kg_score >= 50.0: tahmin = "🔥 2.5 ÜST & KG VAR"
    elif ai_ust_score >= 48.0: tahmin = "⚽ 2.5 ÜST"
    elif ai_kg_score >= 46.0: tahmin = "🤝 KG VAR"

    return tahmin, ai_ust_score, ai_kg_score

# ==========================================
# 2. CANLI BİTEN MAÇLARI DOĞRUDAN API'DEN TESPİT ETME
# ==========================================
def api_canli_biten_maclari_kontrol_et(chat_id=None):
    """Veritabanına ihtiyaç duymadan doğrudan API'den biten maçları kontrol eder."""
    su_an = datetime.utcnow() + timedelta(hours=3)
    tarih_str = su_an.strftime("%Y-%m-%d")

    url = f"{BASE_URL}/fixtures"
    params = {"date": tarih_str, "timezone": "Europe/Istanbul"}
    
    try:
        res = requests.get(url, params=params, headers=HEADERS, timeout=30)
        data = res.json().get("response", [])
        if not data:
            if chat_id: telegram_post("ℹ️ Bugün için maç verisi bulunamadı.", chat_id)
            return

        biten_maclar = [m for m in data if m["fixture"]["status"]["short"] in ['FT', 'AET', 'PEN']]
        if not biten_maclar:
            if chat_id: telegram_post("ℹ️ Şu an henüz sonuçlanmış yeni bir maç bulunmuyor.", chat_id)
            return

        yeni_bildirim_var = False

        for m in biten_maclar:
            fid = m["fixture"]["id"]
            if fid in BILDIRILEN_MACLAR:
                continue # Daha önce gruba bildirildiyse atla

            lig = m["league"]["name"]
            lid = m["league"]["id"]
            ev = m["teams"]["home"]["name"]
            dep = m["teams"]["away"]["name"]
            ev_gol = m["goals"]["home"] if m["goals"]["home"] is not None else 0
            dep_gol = m["goals"]["away"] if m["goals"]["away"] is not None else 0

            # Tahmin hesaplaması için varsayılan oranlar/analiz üret
            tahmin, _, _ = tahmin_ve_oran_hesapla(lid, None, None)

            toplam_gol = ev_gol + dep_gol
            kg_durum = (ev_gol > 0 and dep_gol > 0)
            basarili = False

            if "2.5 ÜST & KG VAR" in tahmin:
                if toplam_gol >= 3 and kg_durum: basarili = True
            elif "2.5 ÜST" in tahmin:
                if toplam_gol >= 3: basarili = True
            elif "KG VAR" in tahmin:
                if kg_durum: basarili = True

            durum_emoji = "✅ KAZANDI" if basarili else "❌ KAYBETTİ"

            mesaj = (
                f"🏁 <b>MAÇ SONUÇLANDI!</b>\n"
                f"🏆 <code>{lig}</code>\n"
                f"⚔️ <b>{ev} {ev_gol} - {dep_gol} {dep}</b>\n"
                f"🎯 <b>AI Tahmini:</b> {tahmin}\n"
                f"📌 <b>Sonuç:</b> {durum_emoji}"
            )
            
            telegram_post(mesaj, chat_id)
            BILDIRILEN_MACLAR.add(fid)
            yeni_bildirim_var = True
            time.sleep(1) # Telegram spam engeline takılmamak için kısa bekleme

        if not yeni_bildirim_var and chat_id:
            telegram_post("ℹ️ Sonuçlanan tüm maçlar zaten gruba bildirildi.", chat_id)

    except Exception as e:
        print("Biten mac kontrol hatasi:", e)

# ==========================================
# 3. BÜLTEN VE ANALİZ ÇIKARMA
# ==========================================
def bot_bulten_gorevi(chat_id):
    su_an = datetime.utcnow() + timedelta(hours=3)
    tarih_str = su_an.strftime("%Y-%m-%d")
    saat_str = su_an.strftime("%H:%M")

    telegram_post("⏳ <b>Güncel canlı ve yaklaşan maçlar taranıyor...</b> Lütfen bekleyin.", chat_id)
    
    url = f"{BASE_URL}/fixtures"
    params = {"date": tarih_str, "timezone": "Europe/Istanbul"}
    
    try:
        res = requests.get(url, params=params, headers=HEADERS, timeout=30)
        data = res.json().get("response", [])
        
        # Oynanmamış veya canlı olan maçları filtrele
        uygun_maclar = [
            m for m in data 
            if m["fixture"]["status"]["short"] in ['NS', '1H', 'HT', '2H', 'LIVE'] 
            and m["fixture"]["date"][11:16] >= saat_str
        ]

        if not uygun_maclar:
            telegram_post("⚠️ Saat bazlı analiz edilecek aktif maç bulunamadı.", chat_id)
            return

        baslik = f"🤖 <b>AI FOOTBALL BÜLTENİ</b> ({tarih_str})\n⏰ <i>Saat {saat_str} (TSİ) Sonrası ({len(uygun_maclar[:15])} Maç)</i>\n=============================\n\n"
        parca_mesaj = baslik

        for m in uygun_maclar[:15]: # Grubu boğmamak için ilk 15 maçı sunar
            durum = m["fixture"]["status"]["short"]
            saat = m["fixture"]["date"][11:16]
            lig = m["league"]["name"]
            lid = m["league"]["id"]
            ev = m["teams"]["home"]["name"]
            dep = m["teams"]["away"]["name"]

            durum_etiketi = "🔴 CANLI" if durum in ['1H', '2H', 'HT', 'LIVE'] else f"⏰ {saat}"
            tahmin, ai_ust, ai_kg = tahmin_ve_oran_hesapla(lid, None, None)

            mac_metni = (
                f"{durum_etiketi} | 🏆 <code>{lig}</code>\n"
                f"⚔️ <b>{ev} vs {dep}</b>\n"
                f"🎯 <b>AI TAHMİNİ:</b> <u>{tahmin}</u>\n"
                f"📈 <b>2.5 Üst Güveni:</b> %{ai_ust}\n"
                f"⚽ <b>KG Var Güveni:</b> %{ai_kg}\n"
                f"-----------------------------------------\n"
            )
            if len(parca_mesaj) + len(mac_metni) > 3800:
                telegram_post(parca_mesaj, chat_id)
                parca_mesaj = ""
            parca_mesaj += mac_metni

        if parca_mesaj: telegram_post(parca_mesaj, chat_id)

    except Exception as e:
        telegram_post(f"❌ Analiz hatası: {str(e)}", chat_id)

# ==========================================
# 4. ARKA PLAN ZAMANLAYICISI
# ==========================================
scheduler = BackgroundScheduler()
# Her 5 dakikada bir otomatik canlı skor kontrolü yapar
scheduler.add_job(func=api_canli_biten_maclari_kontrol_et, trigger="interval", minutes=5)
scheduler.start()

# ==========================================
# 5. FLASK WEBHOOK
# ==========================================
@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json()
    if update and "message" in update:
        message = update["message"]
        text = message.get("text", "").strip()
        chat_id = message["chat"]["id"]
        
        if text.lower() == "!analiz":
            threading.Thread(target=bot_bulten_gorevi, args=(chat_id,)).start()
        elif text.lower() == "!sonuc":
            threading.Thread(target=api_canli_biten_maclari_kontrol_et, args=(chat_id,)).start()
            
    return jsonify({"status": "ok"}), 200

@app.route('/', methods=['GET'])
def home():
    return "AI Football Bot - Canlı Takip Servisi Aktif!", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
