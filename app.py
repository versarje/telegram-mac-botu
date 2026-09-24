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

# Mükerrer bildirim engelleme ve kota takip hafızası
YARIM_SAAT_BILDIRILENLER = set()
CANLI_TAKIP_HAFIZASI = {} # { fixture_id: {"home_goals": 0, "away_goals": 0, "status": "1H"} }

KOTA_TAKIP = {
    "bugun_tarih": datetime.utcnow().strftime("%Y-%m-%d"),
    "harcanan_istek": 0,
    "max_limit": 100
}

# ==========================================
# 1. YARDIMCI FONKSİYONLAR & KOTA YÖNETİMİ
# ==========================================
def api_request(endpoint, params=None):
    """API isteklerini kota sayacını güncelleyerek güvenle yapar."""
    global KOTA_TAKIP
    bugun = datetime.utcnow().strftime("%Y-%m-%d")
    
    # Gün değiştiyse kotayı sıfırla
    if KOTA_TAKIP["bugun_tarih"] != bugun:
        KOTA_TAKIP["bugun_tarih"] = bugun
        KOTA_TAKIP["harcanan_istek"] = 0

    if KOTA_TAKIP["harcanan_istek"] >= KOTA_TAKIP["max_limit"]:
        print("⚠️ GÜNLÜK API KOTASI DOLDU! İstek engellendi.")
        return None

    url = f"{BASE_URL}/{endpoint}"
    try:
        res = requests.get(url, params=params, headers=HEADERS, timeout=30)
        KOTA_TAKIP["harcanan_istek"] += 1
        return res.json()
    except Exception as e:
        print("API İSTEK HATASI:", e)
        return None

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

def tahmin_ve_oran_hesapla(lid, ust25=1.80, kg_var=1.80):
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
# 2. SİSTEM 1: YAKLAŞAN MAÇLARI TARAMA (30 DK KALAN)
# ==========================================
def yaklasan_maclari_kontrol_et():
    """Başlamasına ~30 dakika kalan maçları tespit eder ve tahminini gruba atar."""
    su_an = datetime.utcnow()
    tarih_str = (su_an + timedelta(hours=3)).strftime("%Y-%m-%d")

    res_data = api_request("fixtures", {"date": tarih_str, "timezone": "UTC"})
    if not res_data: return
    
    data = res_data.get("response", [])
    
    for m in data:
        fid = m["fixture"]["id"]
        status = m["fixture"]["status"]["short"]
        
        if status != 'NS' or fid in YARIM_SAAT_BILDIRILENLER:
            continue

        mac_zamani = datetime.fromisoformat(m["fixture"]["date"].replace("Z", "+00:00")).replace(tzinfo=None)
        fark_dakika = (mac_zamani - su_an).total_seconds() / 60.0

        if 15 <= fark_dakika <= 45:
            lig = m["league"]["name"]
            lid = m["league"]["id"]
            ev = m["teams"]["home"]["name"]
            dep = m["teams"]["away"]["name"]
            saat_tsi = (mac_zamani + timedelta(hours=3)).strftime("%H:%M")

            tahmin, ai_ust, ai_kg = tahmin_ve_oran_hesapla(lid)

            mesaj = (
                f"⏳ <b>MAÇ BAŞLIYOR! (Bülten Tahmini)</b>\n"
                f"🏆 <code>{lig}</code>\n"
                f"⚔️ <b>{ev} vs {dep}</b>\n"
                f"⏰ Saat: <b>{saat_tsi}</b>\n"
                f"-----------------------------------------\n"
                f"🎯 <b>AI TAHMİNİ:</b> <u>{tahmin}</u>\n"
                f"📈 2.5 Üst: %{ai_ust} | ⚽ KG Var: %{ai_kg}\n"
                f"⚡ <i>Canlı takibe alındı!</i>"
            )
            telegram_post(mesaj)
            YARIM_SAAT_BILDIRILENLER.add(fid)

# ==========================================
# 3. SİSTEM 2: CANLI MAÇ SKOR & SÜREÇ TAKİBİ
# ==========================================
def canlı_mac_olaylarini_takip_et():
    """Tüm canlı maçları tek sorguda çeker; Gol, İY bitti, 2Y başladı ve MS durumlarını bildirir."""
    res_data = api_request("fixtures", {"live": "all"})
    if not res_data: return
    
    data = res_data.get("response", [])
    
    for m in data:
        fid = m["fixture"]["id"]
        lig = m["league"]["name"]
        ev = m["teams"]["home"]["name"]
        dep = m["teams"]["away"]["name"]
        
        yeni_ev_gol = m["goals"]["home"] if m["goals"]["home"] is not None else 0
        yeni_dep_gol = m["goals"]["away"] if m["goals"]["away"] is not None else 0
        
        yeni_durum = m["fixture"]["status"]["short"]
        dakika = m["fixture"]["status"]["elapsed"]
        dakika_str = f"{dakika}'" if dakika else ""

        if fid not in CANLI_TAKIP_HAFIZASI:
            CANLI_TAKIP_HAFIZASI[fid] = {
                "home_goals": yeni_ev_gol,
                "away_goals": yeni_dep_gol,
                "status": yeni_durum
            }
            if yeni_durum == '1H' and (yeni_ev_gol + yeni_dep_gol == 0):
                telegram_post(f"🎬 <b>MAÇ BAŞLADI!</b>\n🏆 <code>{lig}</code>\n⚔️ <b>{ev} 0 - 0 {dep}</b>")
            continue

        eski_veri = CANLI_TAKIP_HAFIZASI[fid]

        # A. GOL BİLDİRİMİ
        if yeni_ev_gol > eski_veri["home_goals"] or yeni_dep_gol > eski_veri["away_goals"]:
            atılan_taraf = ev if yeni_ev_gol > eski_veri["home_goals"] else dep
            mesaj = (
                f"⚽ <b>GOL!</b> ({dakika_str})\n"
                f"🏆 <code>{lig}</code>\n"
                f"⚔️ <b>{ev} {yeni_ev_gol} - {yeni_dep_gol} {dep}</b>\n"
                f"🔥 Gol: <b>{atılan_taraf}</b>"
            )
            telegram_post(mesaj)

        # B. İLK YARI BİTTİ (HT)
        if yeni_durum == 'HT' and eski_veri["status"] != 'HT':
            mesaj = (
                f"⏸️ <b>İLK YARI BİTTİ</b>\n"
                f"🏆 <code>{lig}</code>\n"
                f"⚔️ <b>{ev} {yeni_ev_gol} - {yeni_dep_gol} {dep}</b>"
            )
            telegram_post(mesaj)

        # C. İKİNCİ YARI BAŞLADI (2H)
        if yeni_durum == '2H' and eski_veri["status"] != '2H':
            mesaj = (
                f"▶️ <b>İKİNCİ YARI BAŞLADI</b>\n"
                f"🏆 <code>{lig}</code>\n"
                f"⚔️ <b>{ev} {yeni_ev_gol} - {yeni_dep_gol} {dep}</b>"
            )
            telegram_post(mesaj)

        # D. MAÇ BİTTİ (FT)
        if yeni_durum in ['FT', 'AET', 'PEN'] and eski_veri["status"] not in ['FT', 'AET', 'PEN']:
            mesaj = (
                f"🏁 <b>MAÇ SONA ERDİ</b>\n"
                f"🏆 <code>{lig}</code>\n"
                f"⚔️ <b>{ev} {yeni_ev_gol} - {yeni_dep_gol} {dep}</b>"
            )
            telegram_post(mesaj)

        CANLI_TAKIP_HAFIZASI[fid] = {
            "home_goals": yeni_ev_gol,
            "away_goals": yeni_dep_gol,
            "status": yeni_durum
        }

# ==========================================
# 4. MANUEL KOMUT FONKSİYONLARI (!canli ve !kota)
# ==========================================
def manuel_canli_skorlar_getir(chat_id):
    """!canli yazıldığında o an oynanan maçları listeler."""
    res_data = api_request("fixtures", {"live": "all"})
    if not res_data or not res_data.get("response"):
        telegram_post("🔴 Şu anda oynanan canlı maç bulunmuyor.", chat_id)
        return

    data = res_data.get("response", [])
    satirlar = [f"🔴 <b>CANLI MAÇLAR ({len(data)} Maç)</b>\n"]
    
    for m in data[:15]: # Telegram mesaj sınırı için ilk 15 maç
        ev = m["teams"]["home"]["name"]
        dep = m["teams"]["away"]["name"]
        ev_g = m["goals"]["home"] if m["goals"]["home"] is not None else 0
        dep_g = m["goals"]["away"] if m["goals"]["away"] is not None else 0
        dakika = m["fixture"]["status"]["elapsed"]
        dak_str = f"{dakika}'" if dakika else m["fixture"]["status"]["short"]

        satirlar.append(f"⏱ <b>{dak_str}</b> | {ev} <b>{ev_g} - {dep_g}</b> {dep}")

    telegram_post("\n".join(satirlar), chat_id)

def manuel_kota_bilgisi_getir(chat_id):
    """!kota yazıldığında kalan API hakkını bildirir."""
    harcanan = KOTA_TAKIP["harcanan_istek"]
    limit = KOTA_TAKIP["max_limit"]
    kalan = max(0, limit - harcanan)
    yuzde = int((harcanan / limit) * 100)

    mesaj = (
        f"📊 <b>API KOTA DURUMU</b>\n"
        f"-----------------------------------------\n"
        f"📅 Tarih: <b>{KOTA_TAKIP['bugun_tarih']}</b>\n"
        f"📉 Harcanan İstek: <b>{harcanan} / {limit}</b>\n"
        f"🔋 Kalan Hakkınız: <b>{kalan} İstek</b>\n"
        f"⚡ Kullanım Oranı: <b>%{yuzde}</b>\n"
        f"-----------------------------------------\n"
        f"💡 <i>Gece 00:00 UTC saatinde kota otomatik sıfırlanır.</i>"
    )
    telegram_post(mesaj, chat_id)

# ==========================================
# 5. KOTA DOSTU ZAMANLAYICI (SCHEDULER)
# ==========================================
scheduler = BackgroundScheduler()

# Yaklaşan maçlar: Her 30 dakikada 1 sorgu
scheduler.add_job(func=yaklasan_maclari_kontrol_et, trigger="interval", minutes=30)

# Canlı maçlar: Her 10 dakikada 1 sorgu
scheduler.add_job(func=canlı_mac_olaylarini_takip_et, trigger="interval", minutes=10)

scheduler.start()

# ==========================================
# 6. FLASK WEBHOOK SERVİSİ
# ==========================================
@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json()
    if update and "message" in update:
        message = update["message"]
        text = message.get("text", "").strip().lower()
        chat_id = message["chat"]["id"]
        
        if text == "!analiz":
            threading.Thread(target=yaklasan_maclari_kontrol_et).start()
            telegram_post("🔎 Yaklaşan maç bülteni taranıyor...", chat_id)

        elif text == "!canli":
            threading.Thread(target=manuel_canli_skorlar_getir, args=(chat_id,)).start()

        elif text == "!kota":
            threading.Thread(target=manuel_kota_bilgisi_getir, args=(chat_id,)).start()

    return jsonify({"status": "ok"}), 200

@app.route('/', methods=['GET'])
def home():
    return "AI Canlı Skor ve Takip Sistemi Aktif!", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
