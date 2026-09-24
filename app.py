import os
import math
import time
import json
import base64
import requests
import threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# ==========================================
# ⚙️ KONFİGÜRASYONLAR & GITHUB DB AYARLARI
# ==========================================
API_KEY = "b699d9effa443321a65fd145ec78ede1"
BASE_URL = "https://v3.football.api-sports.io"
TELEGRAM_BOT_TOKEN = "8894398415:AAEY_ffz8iPL8qZ8vJq3bgat7cibeQFhvI8"
TELEGRAM_CHAT_ID = "-1004461429503"

# GITHUB DATABASE YAPILANDIRMASI
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "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")
GITHUB_REPO = "versarje/telegram-mac-botu"
GITHUB_FILE_PATH = "database.json"

GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
HEADERS_GITHUB = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

HEADERS = {
    "x-apisports-key": API_KEY,
    "Accept": "application/json"
}

LIG_ID_BONUS = [39, 140, 135, 78, 61, 88, 203, 144, 94, 2, 3, 848, 5]

# HAFIZA SİSTEMLERİ
YARIM_SAAT_BILDIRILENLER = set()
CANLI_TAKIP_HAFIZASI = {} 

KOTA_TAKIP = {
    "bugun_tarih": datetime.utcnow().strftime("%Y-%m-%d"),
    "harcanan_istek": 0,
    "max_limit": 100
}

# ==========================================
# 🔄 GITHUB DATABASE OKUMA VE YAZMA SİSTEMİ
# ==========================================
def github_db_oku():
    """GitHub'dan verileri ve SHA anahtarını çeker."""
    try:
        res = requests.get(GITHUB_API_URL, headers=HEADERS_GITHUB, timeout=10)
        if res.status_code == 200:
            content = res.json()
            file_content = base64.b64decode(content["content"]).decode("utf-8")
            return json.loads(file_content), content["sha"]
        else:
            print("GitHub DB Okuma Hatası:", res.status_code)
            return {"tahminler": {}, "ozel_takip": {}}, None
    except Exception as e:
        print("GitHub DB Okuma Istek Hatası:", e)
        return {"tahminler": {}, "ozel_takip": {}}, None

def github_db_yaz(yeni_veri, sha_key):
    """Verileri GitHub'daki database.json dosyasına otomatik commit atarak kaydeder."""
    try:
        json_str = json.dumps(yeni_veri, ensure_ascii=False, indent=2)
        encoded_content = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")

        payload = {
            "message": "🤖 Bot Veri Tabanı Güncellendi [Auto Commit]",
            "content": encoded_content,
            "sha": sha_key
        }

        res = requests.put(GITHUB_API_URL, json=payload, headers=HEADERS_GITHUB, timeout=10)
        if res.status_code in [200, 201]:
            print("✅ Veriler GitHub Database'e başarıyla yazıldı.")
            return True
        else:
            print("❌ GitHub DB Yazma Hatası:", res.status_code, res.json())
            return False
    except Exception as e:
        print("GitHub DB Yazma Istek Hatası:", e)
        return False

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

    tahmin_metni = "⚽ 2.5 ÜST"
    tahmin_turu = "UST25"

    if ai_ust_score >= 52.0 and ai_kg_score >= 50.0: 
        tahmin_metni = "🔥 2.5 ÜST & KG VAR"
        tahmin_turu = "UST_KG"
    elif ai_ust_score >= 48.0: 
        tahmin_metni = "⚽ 2.5 ÜST"
        tahmin_turu = "UST25"
    elif ai_kg_score >= 46.0: 
        tahmin_metni = "🤝 KG VAR"
        tahmin_turu = "KG_VAR"

    return tahmin_metni, tahmin_turu, ai_ust_score, ai_kg_score

# ==========================================
# 2. YAKLAŞAN MAÇLAR VE TAHMİN KAYDI
# ==========================================
def yaklasan_maclari_kontrol_et():
    su_an = datetime.utcnow()
    tarih_str = (su_an + timedelta(hours=3)).strftime("%Y-%m-%d")

    res_data = api_request("fixtures", {"date": tarih_str, "timezone": "UTC"})
    if not res_data: return
    
    data = res_data.get("response", [])
    
    db_veri, sha_key = github_db_oku()
    degisiklik_var_mi = False

    for m in data:
        fid = str(m["fixture"]["id"])
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

            tahmin_metni, tahmin_turu, ai_ust, ai_kg = tahmin_ve_oran_hesapla(lid)

            # GitHub Veri Tabanına Kaydet
            db_veri["tahminler"][fid] = {
                "mac": f"{ev} vs {dep}",
                "tahmin": tahmin_metni,
                "tur": tahmin_turu,
                "skor": "0-0",
                "durum": "⏳ BEKLENİYOR"
            }
            degisiklik_var_mi = True

            mesaj = (
                f"⏳ <b>MAÇ BAŞLIYOR!</b> (ID: <code>{fid}</code>)\n"
                f"🏆 <code>{lig}</code>\n"
                f"⚔️ <b>{ev} vs {dep}</b>\n"
                f"⏰ Saat: <b>{saat_tsi}</b>\n"
                f"-----------------------------------------\n"
                f"🎯 <b>AI TAHMİNİ:</b> <u>{tahmin_metni}</u>\n"
                f"📈 2.5 Üst: %{ai_ust} | ⚽ KG Var: %{ai_kg}\n\n"
                f"📌 <i>Takip etmek için:</i> <code>!takip {fid}</code>"
            )
            telegram_post(mesaj)
            YARIM_SAAT_BILDIRILENLER.add(fid)

    if degisiklik_var_mi and sha_key:
        github_db_yaz(db_veri, sha_key)

# ==========================================
# 3. CANLI MAÇ TAKİBİ VE DUMP
# ==========================================
def canlı_mac_olaylarini_takip_et():
    res_data = api_request("fixtures", {"live": "all"})
    if not res_data: return
    
    data = res_data.get("response", [])
    db_veri, sha_key = github_db_oku()
    degisiklik_var_mi = False
    
    for m in data:
        fid = str(m["fixture"]["id"])
        lig = m["league"]["name"]
        ev = m["teams"]["home"]["name"]
        dep = m["teams"]["away"]["name"]
        
        yeni_ev_gol = m["goals"]["home"] if m["goals"]["home"] is not None else 0
        yeni_dep_gol = m["goals"]["away"] if m["goals"]["away"] is not None else 0
        yeni_durum = m["fixture"]["status"]["short"]
        dakika = m["fixture"]["status"]["elapsed"]
        dakika_str = f"{dakika}'" if dakika else ""

        takipciler = db_veri["ozel_takip"].get(fid, [])
        etiket_metni = f"\n🔔 <b>Takipçiler:</b> {' '.join(takipciler)}" if takipciler else ""

        if fid not in CANLI_TAKIP_HAFIZASI:
            CANLI_TAKIP_HAFIZASI[fid] = {
                "home_goals": yeni_ev_gol,
                "away_goals": yeni_dep_gol,
                "status": yeni_durum
            }
            continue

        eski_veri = CANLI_TAKIP_HAFIZASI[fid]

        # GOL
        if yeni_ev_gol > eski_veri["home_goals"] or yeni_dep_gol > eski_veri["away_goals"]:
            atılan_taraf = ev if yeni_ev_gol > eski_veri["home_goals"] else dep
            telegram_post(
                f"⚽ <b>GOL!</b> ({dakika_str}) [ID: <code>{fid}</code>]\n"
                f"🏆 <code>{lig}</code>\n"
                f"⚔️ <b>{ev} {yeni_ev_gol} - {yeni_dep_gol} {dep}</b>\n"
                f"🔥 Gol: <b>{atılan_taraf}</b>{etiket_metni}"
            )

        # MAÇ BİTTİ -> TAHMİNİ SONUÇLANDIR VE DB'YE YAZ
        if yeni_durum in ['FT', 'AET', 'PEN'] and eski_veri["status"] not in ['FT', 'AET', 'PEN']:
            telegram_post(
                f"🏁 <b>MAÇ SONA ERDİ</b> (ID: <code>{fid}</code>)\n"
                f"🏆 <code>{lig}</code>\n"
                f"⚔️ <b>{ev} {yeni_ev_gol} - {yeni_dep_gol} {dep}</b>{etiket_metni}"
            )

            if fid in db_veri["tahminler"]:
                toplam_gol = yeni_ev_gol + yeni_dep_gol
                kg_var = (yeni_ev_gol > 0 and yeni_dep_gol > 0)
                tur = db_veri["tahminler"][fid]["tur"]
                tuttu = False

                if tur == "UST25" and toplam_gol > 2: tuttu = True
                elif tur == "KG_VAR" and kg_var: tuttu = True
                elif tur == "UST_KG" and (toplam_gol > 2 and kg_var): tuttu = True

                db_veri["tahminler"][fid]["skor"] = f"{yeni_ev_gol}-{yeni_dep_gol}"
                db_veri["tahminler"][fid]["durum"] = "✅ TUTTU" if tuttu else "❌ GELMEDİ"
                degisiklik_var_mi = True

            if fid in db_veri["ozel_takip"]:
                del db_veri["ozel_takip"][fid]
                degisiklik_var_mi = True

        CANLI_TAKIP_HAFIZASI[fid] = {
            "home_goals": yeni_ev_gol,
            "away_goals": yeni_dep_gol,
            "status": yeni_durum
        }

    if degisiklik_var_mi and sha_key:
        github_db_yaz(db_veri, sha_key)

# ==========================================
# 4. SKORBOARD, KOTA VE KOMUTLAR
# ==========================================
def skorboard_getir(chat_id=None):
    target_chat = chat_id if chat_id else TELEGRAM_CHAT_ID
    db_veri, _ = github_db_oku()
    tahminler = db_veri.get("tahminler", {})

    if not tahminler:
        telegram_post("📊 Henüz tahmin yapılmış bir maç bulunmuyor.", target_chat)
        return

    toplam = len(tahminler)
    tutan = sum(1 for v in tahminler.values() if v["durum"] == "✅ TUTTU")
    yatan = sum(1 for v in tahminler.values() if v["durum"] == "❌ GELMEDİ")
    bekleyen = sum(1 for v in tahminler.values() if "BEKLENİYOR" in v["durum"])

    basari_orani = round((tutan / (tutan + yatan)) * 100, 1) if (tutan + yatan) > 0 else 0

    satirlar = [
        "📊 <b>BUGÜNÜN TAHMİN SKORBOARDU (GitHub DB)</b>",
        "-----------------------------------------"
    ]

    for fid, item in tahminler.items():
        satirlar.append(
            f"🔹 <b>{item['mac']}</b> ({item['skor']})\n"
            f"🎯 Tahmin: <i>{item['tahmin']}</i> | Durum: <b>{item['durum']}</b>\n"
        )

    satirlar.append("-----------------------------------------")
    satirlar.append(f"✅ Tutan: <b>{tutan}</b> | ❌ Yatan: <b>{yatan}</b> | ⏳ Bekleyen: <b>{bekleyen}</b>")
    satirlar.append(f"📈 <b>Başarı Oranı: %{basari_orani}</b>")

    telegram_post("\n".join(satirlar), target_chat)

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

def takip_ekle_cikar(user_mention, cmd_args, chat_id):
    if not cmd_args:
        telegram_post(f"⚠️ {user_mention} Örnek kullanım: <code>!takip 1038492</code>", chat_id)
        return

    fid = str(cmd_args[0])
    db_veri, sha_key = github_db_oku()

    if not sha_key:
        telegram_post("⚠️ Veri tabanı bağlantı hatası!", chat_id)
        return

    if fid not in db_veri["ozel_takip"]:
        db_veri["ozel_takip"][fid] = []

    if user_mention in db_veri["ozel_takip"][fid]:
        db_veri["ozel_takip"][fid].remove(user_mention)
        telegram_post(f"❌ {user_mention}, <b>{fid}</b> ID'li maç takipten çıkarıldı.", chat_id)
    else:
        db_veri["ozel_takip"][fid].append(user_mention)
        telegram_post(f"✅ {user_mention}, <b>{fid}</b> ID'li maç takibe alındı!", chat_id)

    # Güncellenen Takipçi Listesini GitHub'a Yaz
    github_db_yaz(db_veri, sha_key)

# ==========================================
# 5. SCHEDULER & FLASK WEBHOOK
# ==========================================
scheduler = BackgroundScheduler()
# Yaklaşan maç kontrolü (Her 30 dakikada bir)
scheduler.add_job(func=yaklasan_maclari_kontrol_et, trigger="interval", minutes=30)
# Canlı maç kontrolü (Her 10 dakikada bir)
scheduler.add_job(func=canlı_mac_olaylarini_takip_et, trigger="interval", minutes=10)
# Gece Otomatik Skorboard Raporı (Her gece 23:59'da Telegram Grubuna atar)
scheduler.add_job(func=lambda: skorboard_getir(TELEGRAM_CHAT_ID), trigger="cron", hour=23, minute=59)

scheduler.start()

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json()
    if update and "message" in update:
        message = update["message"]
        text = message.get("text", "").strip()
        chat_id = message["chat"]["id"]
        
        from_user = message.get("from", {})
        username = from_user.get("username")
        user_mention = f"@{username}" if username else from_user.get("first_name", "Kullanıcı")

        parcalar = text.split()
        komut = parcalar[0].lower() if parcalar else ""

        if komut in ["!skorboard", "!tahminler"]:
            threading.Thread(target=skorboard_getir, args=(chat_id,)).start()

        elif komut == "!takip":
            threading.Thread(target=takip_ekle_cikar, args=(user_mention, parcalar[1:], chat_id)).start()

        elif komut == "!kota":
            threading.Thread(target=manuel_kota_bilgisi_getir, args=(chat_id,)).start()

    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
