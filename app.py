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

# HAFIZA SİSTEMİ
YARIM_SAAT_BILDIRILENLER = set()
CANLI_TAKIP_HAFIZASI = {} 

# Takip Eden Kullanıcılar -> { fixture_id: set( user_mention_1, user_mention_2 ) }
OZEL_TAKIP_LISTESI = {}

KOTA_TAKIP = {
    "bugun_tarih": datetime.utcnow().strftime("%Y-%m-%d"),
    "harcanan_istek": 0,
    "max_limit": 100
}

# ==========================================
# 1. YARDIMCI FONKSİYONLAR
# ==========================================
def api_request(endpoint, params=None):
    global KOTA_TAKIP
    bugun = datetime.utcnow().strftime("%Y-%m-%d")
    
    if KOTA_TAKIP["bugun_tarih"] != bugun:
        KOTA_TAKIP["bugun_tarih"] = bugun
        KOTA_TAKIP["harcanan_istek"] = 0

    if KOTA_TAKIP["harcanan_istek"] >= KOTA_TAKIP["max_limit"]:
        print("⚠️ GÜNLÜK API KOTASI DOLDU!")
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
# 2. YAKLAŞAN MAÇLAR KONTROLÜ
# ==========================================
def yaklasan_maclari_kontrol_et():
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
                f"⏳ <b>MAÇ BAŞLIYOR!</b> (ID: <code>{fid}</code>)\n"
                f"🏆 <code>{lig}</code>\n"
                f"⚔️ <b>{ev} vs {dep}</b>\n"
                f"⏰ Saat: <b>{saat_tsi}</b>\n"
                f"-----------------------------------------\n"
                f"🎯 <b>AI TAHMİNİ:</b> <u>{tahmin}</u>\n"
                f"📈 2.5 Üst: %{ai_ust} | ⚽ KG Var: %{ai_kg}\n\n"
                f"📌 <i>Bu maçı takibe almak için:</i> <code>!takip {fid}</code>"
            )
            telegram_post(mesaj)
            YARIM_SAAT_BILDIRILENLER.add(fid)

# ==========================================
# 3. CANLI MAÇ TAKİBİ VE ÖZEL BİLDİRİM
# ==========================================
def canlı_mac_olaylarini_takip_et():
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

        # Özel takipçiler var mı bak
        takipciler = OZEL_TAKIP_LISTESI.get(fid, set())
        etiket_metni = ""
        if takipciler:
            etiket_metni = "\n🔔 <b>Takipçiler:</b> " + " ".join(takipciler)

        if fid not in CANLI_TAKIP_HAFIZASI:
            CANLI_TAKIP_HAFIZASI[fid] = {
                "home_goals": yeni_ev_gol,
                "away_goals": yeni_dep_gol,
                "status": yeni_durum
            }
            if yeni_durum == '1H' and (yeni_ev_gol + yeni_dep_gol == 0):
                telegram_post(f"🎬 <b>MAÇ BAŞLADI!</b> (ID: <code>{fid}</code>)\n🏆 <code>{lig}</code>\n⚔️ <b>{ev} 0 - 0 {dep}</b>{etiket_metni}")
            continue

        eski_veri = CANLI_TAKIP_HAFIZASI[fid]

        # GOL
        if yeni_ev_gol > eski_veri["home_goals"] or yeni_dep_gol > eski_veri["away_goals"]:
            atılan_taraf = ev if yeni_ev_gol > eski_veri["home_goals"] else dep
            mesaj = (
                f"⚽ <b>GOL!</b> ({dakika_str}) [ID: <code>{fid}</code>]\n"
                f"🏆 <code>{lig}</code>\n"
                f"⚔️ <b>{ev} {yeni_ev_gol} - {yeni_dep_gol} {dep}</b>\n"
                f"🔥 Gol: <b>{atılan_taraf}</b>"
                f"{etiket_metni}"
            )
            telegram_post(mesaj)

        # İLK YARI BİTTİ
        if yeni_durum == 'HT' and eski_veri["status"] != 'HT':
            mesaj = (
                f"⏸️ <b>İLK YARI BİTTİ</b> (ID: <code>{fid}</code>)\n"
                f"🏆 <code>{lig}</code>\n"
                f"⚔️ <b>{ev} {yeni_ev_gol} - {yeni_dep_gol} {dep}</b>"
                f"{etiket_metni}"
            )
            telegram_post(mesaj)

        # İKİNCİ YARI BAŞLADI
        if yeni_durum == '2H' and eski_veri["status"] != '2H':
            mesaj = (
                f"▶️ <b>İKİNCİ YARI BAŞLADI</b> (ID: <code>{fid}</code>)\n"
                f"🏆 <code>{lig}</code>\n"
                f"⚔️ <b>{ev} {yeni_ev_gol} - {yeni_dep_gol} {dep}</b>"
                f"{etiket_metni}"
            )
            telegram_post(mesaj)

        # MAÇ BİTTİ
        if yeni_durum in ['FT', 'AET', 'PEN'] and eski_veri["status"] not in ['FT', 'AET', 'PEN']:
            mesaj = (
                f"🏁 <b>MAÇ SONA ERDİ</b> (ID: <code>{fid}</code>)\n"
                f"🏆 <code>{lig}</code>\n"
                f"⚔️ <b>{ev} {yeni_ev_gol} - {yeni_dep_gol} {dep}</b>"
                f"{etiket_metni}"
            )
            telegram_post(mesaj)
            # Maç bitince takip listesinden temizle
            if fid in OZEL_TAKIP_LISTESI:
                del OZEL_TAKIP_LISTESI[fid]

        CANLI_TAKIP_HAFIZASI[fid] = {
            "home_goals": yeni_ev_gol,
            "away_goals": yeni_dep_gol,
            "status": yeni_durum
        }

# ==========================================
# 4. ÖZEL TAKİP VE MANUEL KOMUTLAR
# ==========================================
def takip_ekle_cikar(user_mention, cmd_args, chat_id):
    """!takip <ID> komutunu işler."""
    if not cmd_args:
        telegram_post(f"⚠️ {user_mention} Lütfen takip etmek istediğiniz maç ID'sini yazın. Örnek: <code>!takip 1038492</code>", chat_id)
        return

    try:
        fid = int(cmd_args[0])
    except ValueError:
        telegram_post(f"⚠️ {user_mention} Geçersiz Maç ID'si!", chat_id)
        return

    if fid not in OZEL_TAKIP_LISTESI:
        OZEL_TAKIP_LISTESI[fid] = set()

    if user_mention in OZEL_TAKIP_LISTESI[fid]:
        OZEL_TAKIP_LISTESI[fid].remove(user_mention)
        telegram_post(f"❌ {user_mention}, <b>{fid}</b> ID'li maç takip listenizden çıkarıldı.", chat_id)
    else:
        OZEL_TAKIP_LISTESI[fid].add(user_mention)
        telegram_post(f"✅ {user_mention}, <b>{fid}</b> ID'li maç kişisel takip listenize eklendi! Gol olduğunda etiketleneceksiniz.", chat_id)

def manuel_canli_skorlar_getir(chat_id):
    res_data = api_request("fixtures", {"live": "all"})
    if not res_data or not res_data.get("response"):
        telegram_post("🔴 Şu anda oynanan canlı maç bulunmuyor.", chat_id)
        return

    data = res_data.get("response", [])
    satirlar = [f"🔴 <b>CANLI MAÇLAR ({len(data)} Maç)</b>\n"]
    
    for m in data[:15]:
        fid = m["fixture"]["id"]
        ev = m["teams"]["home"]["name"]
        dep = m["teams"]["away"]["name"]
        ev_g = m["goals"]["home"] if m["goals"]["home"] is not None else 0
        dep_g = m["goals"]["away"] if m["goals"]["away"] is not None else 0
        dakika = m["fixture"]["status"]["elapsed"]
        dak_str = f"{dakika}'" if dakika else m["fixture"]["status"]["short"]

        satirlar.append(f"⏱ <b>{dak_str}</b> | {ev} <b>{ev_g} - {dep_g}</b> {dep} (ID: <code>{fid}</code>)")

    telegram_post("\n".join(satirlar), chat_id)

def manuel_kota_bilgisi_getir(chat_id):
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
        f"⚡ Kullanım Oranı: <b>%{yuzde}</b>"
    )
    telegram_post(mesaj, chat_id)

# ==========================================
# 5. SCHEDULER (KOTA DOSTU)
# ==========================================
scheduler = BackgroundScheduler()
scheduler.add_job(func=yaklasan_maclari_kontrol_et, trigger="interval", minutes=30)
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
        text = message.get("text", "").strip()
        chat_id = message["chat"]["id"]
        
        # Kullanıcı Adı Belirleme
        from_user = message.get("from", {})
        username = from_user.get("username")
        user_mention = f"@{username}" if username else from_user.get("first_name", "Kullanıcı")

        parcalar = text.split()
        komut = parcalar[0].lower() if parcalar else ""

        if komut == "!analiz":
            threading.Thread(target=yaklasan_maclari_kontrol_et).start()
            telegram_post("🔎 Yaklaşan maç bülteni taranıyor...", chat_id)

        elif komut == "!canli":
            threading.Thread(target=manuel_canli_skorlar_getir, args=(chat_id,)).start()

        elif komut == "!kota":
            threading.Thread(target=manuel_kota_bilgisi_getir, args=(chat_id,)).start()

        elif komut == "!takip":
            cmd_args = parcalar[1:]
            threading.Thread(target=takip_ekle_cikar, args=(user_mention, cmd_args, chat_id)).start()

    return jsonify({"status": "ok"}), 200

@app.route('/', methods=['GET'])
def home():
    return "AI Canlı Skor ve Takip Sistemi Aktif!", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
