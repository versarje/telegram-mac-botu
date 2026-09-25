import os
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

KOTA_TAKIP = {
    "bugun_tarih": (datetime.utcnow() + timedelta(hours=3)).strftime("%Y-%m-%d"),
    "harcanan_istek": 0,
    "max_limit": 100
}

# ==========================================
# 🔄 GITHUB DATABASE OKUMA VE YAZMA SİSTEMİ
# ==========================================
def github_db_oku():
    try:
        res = requests.get(GITHUB_API_URL, headers=HEADERS_GITHUB, timeout=10)
        if res.status_code == 200:
            content = res.json()
            file_content = base64.b64decode(content["content"]).decode("utf-8")
            data = json.loads(file_content)
            if "tahminler" not in data: data["tahminler"] = {}
            if "bulten" not in data: data["bulten"] = {}
            return data, content["sha"]
        else:
            return {"tahminler": {}, "bulten": {}}, None
    except Exception as e:
        print("GitHub DB Okuma Hatası:", e)
        return {"tahminler": {}, "bulten": {}}, None

def github_db_yaz(yeni_veri, sha_key):
    try:
        json_str = json.dumps(yeni_veri, ensure_ascii=False, indent=2)
        encoded_content = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")

        payload = {
            "message": "🤖 Bot Veri Tabanı Güncellendi",
            "content": encoded_content,
            "sha": sha_key
        }

        res = requests.put(GITHUB_API_URL, json=payload, headers=HEADERS_GITHUB, timeout=10)
        return res.status_code in [200, 201]
    except Exception as e:
        print("GitHub DB Yazma Hatası:", e)
        return False

# ==========================================
# 1. YARDIMCI FONKSİYONLAR
# ==========================================
def api_request(endpoint, params=None):
    global KOTA_TAKIP
    bugun = (datetime.utcnow() + timedelta(hours=3)).strftime("%Y-%m-%d")
    
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

def mac_oranlarini_getir(fixture_id):
    data = api_request("odds", {"fixture": fixture_id})
    ust25_oran, alt25_oran, kg_var_oran = None, None, None

    if data and data.get("response"):
        try:
            bookmakers = data["response"][0].get("bookmakers", [])
            if bookmakers:
                bets = bookmakers[0].get("bets", [])
                for bet in bets:
                    if bet["id"] == 5 or bet["name"] == "Goals Over/Under":
                        for val in bet["values"]:
                            if val["value"] == "Over 2.5":
                                ust25_oran = float(val["odd"])
                            elif val["value"] == "Under 2.5":
                                alt25_oran = float(val["odd"])
                    elif bet["id"] == 8 or bet["name"] == "Both Teams To Score":
                        for val in bet["values"]:
                            if val["value"] == "Yes":
                                kg_var_oran = float(val["odd"])
        except Exception as e:
            print(f"Oran okuma hatasi (ID: {fixture_id}):", e)

    return ust25_oran, alt25_oran, kg_var_oran

def tahmin_ve_oran_hesapla(lid, ust25=None, alt25=None, kg_var=None):
    eff_ust = ust25 if ust25 else 1.65
    eff_alt = alt25 if alt25 else (2.10 if eff_ust < 2.0 else 1.65)
    eff_kg = kg_var if kg_var else 1.65

    if (eff_ust >= 3.00 and 1.40 <= eff_alt <= 1.75) or (1.40 <= eff_alt <= 1.75 and eff_ust > 2.00):
        return "🛡️ 2.5 ALT", "ALT25", round((1 / eff_alt) * 100, 1), round((1 / eff_kg) * 100, 1)

    ust_uygun = (1.40 <= eff_ust <= 1.75)
    kg_uygun = (1.40 <= eff_kg <= 1.75)

    if ust_uygun and kg_uygun:
        if eff_ust <= eff_kg:
            tahmin_metni, tahmin_turu = "⚽ 2.5 ÜST", "UST25"
        else:
            tahmin_metni, tahmin_turu = "🤝 KG VAR", "KG_VAR"
    elif ust_uygun:
        tahmin_metni, tahmin_turu = "⚽ 2.5 ÜST", "UST25"
    elif kg_uygun:
        tahmin_metni, tahmin_turu = "🤝 KG VAR", "KG_VAR"
    else:
        if eff_ust < eff_kg:
            tahmin_metni, tahmin_turu = "⚽ 2.5 ÜST", "UST25"
        else:
            tahmin_metni, tahmin_turu = "🤝 KG VAR", "KG_VAR"

    prob_ust = round((1 / eff_ust) * 100, 1)
    prob_kg = round((1 / eff_kg) * 100, 1)

    return tahmin_metni, tahmin_turu, prob_ust, prob_kg

# ==========================================
# 2. GÜNÜN BÜLTENİ
# ==========================================
def gunun_bulteni(chat_id=None):
    su_an_tsi = datetime.utcnow() + timedelta(hours=3)
    tarih_str = su_an_tsi.strftime("%Y-%m-%d")

    res_data = api_request("fixtures", {"date": tarih_str, "timezone": "Europe/Istanbul"})
    if not res_data or not res_data.get("response"):
        telegram_post("📅 Bugün için bültende maç bulunamadı veya API kotası doldu.", chat_id)
        return

    data = res_data.get("response", [])
    db_veri, sha_key = github_db_oku()
    
    if "bulten" not in db_veri: db_veri["bulten"] = {}
    if "tahminler" not in db_veri: db_veri["tahminler"] = {}

    maclar_listesi = []
    degisiklik_var_mi = False

    for m in data:
        fid = str(m["fixture"]["id"])
        status = m["fixture"]["status"]["short"]
        lig = m["league"]["name"]
        ev = m["teams"]["home"]["name"]
        dep = m["teams"]["away"]["name"]
        
        ev_gol = m["goals"]["home"] if m["goals"]["home"] is not None else 0
        dep_gol = m["goals"]["away"] if m["goals"]["away"] is not None else 0
        
        mac_zamani_raw = m["fixture"]["date"]
        try:
            saat_tsi = datetime.fromisoformat(mac_zamani_raw).strftime("%H:%M")
        except:
            saat_tsi = mac_zamani_raw[11:16]

        durum_str = ""
        if status in ['FT', 'AET', 'PEN']:
            durum_str = f"🏁 <b>BİTTİ ({ev_gol}-{dep_gol})</b>"
        elif status in ['1H', 'HT', '2H', 'ET', 'BT', 'P']:
            elapsed = m["fixture"]["status"]["elapsed"]
            durum_str = f"🔥 <b>CANLI ({elapsed}' | {ev_gol}-{dep_gol})</b>"
        else:
            durum_str = f"⏰ Saat: <b>{saat_tsi}</b>"

        # Biten Maçların Tahmin Durumlarını Güncelle
        if status in ['FT', 'AET', 'PEN'] and fid in db_veri["tahminler"]:
            if db_veri["tahminler"][fid]["durum"] == "⏳ BEKLENİYOR":
                toplam_gol = ev_gol + dep_gol
                kg_var = (ev_gol > 0 and dep_gol > 0)
                tur = db_veri["tahminler"][fid]["tur"]
                tuttu = False

                if tur == "UST25" and toplam_gol > 2: tuttu = True
                elif tur == "ALT25" and toplam_gol < 3: tuttu = True
                elif tur == "KG_VAR" and kg_var: tuttu = True

                db_veri["tahminler"][fid]["skor"] = f"{ev_gol}-{dep_gol}"
                db_veri["tahminler"][fid]["durum"] = "✅ TUTTU" if tuttu else "❌ GELMEDİ"
                degisiklik_var_mi = True

        maclar_listesi.append(
            f"{durum_str} | ID: <code>{fid}</code>\n"
            f"🏆 {lig}\n"
            f"⚔️ <b>{ev} vs {dep}</b>\n"
        )

    if degisiklik_var_mi and sha_key:
        github_db_yaz(db_veri, sha_key)

    if not maclar_listesi:
        telegram_post("📅 Bugün gösterilecek maç bulunamadı.", chat_id)
        return

    mesaj = f"📅 <b>BUGÜNÜN MAÇ BÜLTENİ ({tarih_str})</b>\n-----------------------------------------\n"
    mesaj += "\n".join(maclar_listesi[:15])
    
    if len(maclar_listesi) > 15:
        mesaj += f"\n\n<i>...ve {len(maclar_listesi) - 15} maç daha bültende mevcut.</i>"

    telegram_post(mesaj, chat_id)

# ==========================================
# 3. SKORBOARD, KOTA VE ANALİZ
# ==========================================
def analiz_getir(cmd_args, chat_id):
    if not cmd_args:
        telegram_post("📌 Kullanım: <code>!analiz <MAÇ_ID></code>", chat_id)
        return

    fid = str(cmd_args[0])
    res = api_request("fixtures", {"id": fid})

    if not res or not res.get("response"):
        telegram_post(f"❌ <b>{fid}</b> ID'li maç verisi bulunamadı.", chat_id)
        return

    m = res["response"][0]
    lig = m["league"]["name"]
    ev = m["teams"]["home"]["name"]
    dep = m["teams"]["away"]["name"]
    durum = m["fixture"]["status"]["long"]
    ev_gol = m["goals"]["home"] if m["goals"]["home"] is not None else 0
    dep_gol = m["goals"]["away"] if m["goals"]["away"] is not None else 0

    ust25_o, alt25_o, kg_var_o = mac_oranlarini_getir(fid)
    tahmin_metni, tahmin_turu, ai_ust, ai_kg = tahmin_ve_oran_hesapla(
        m["league"]["id"], ust25=ust25_o, alt25=alt25_o, kg_var=kg_var_o
    )

    # Analiz yapılan maçı veritabanına kaydet
    db_veri, sha_key = github_db_oku()
    if "tahminler" not in db_veri: db_veri["tahminler"] = {}
    
    db_veri["tahminler"][fid] = {
        "mac": f"{ev} vs {dep}",
        "tahmin": tahmin_metni,
        "tur": tahmin_turu,
        "skor": f"{ev_gol}-{dep_gol}",
        "durum": "⏳ BEKLENİYOR"
    }
    if sha_key:
        github_db_yaz(db_veri, sha_key)

    mesaj = (
        f"🔍 <b>MAÇ DETAYLI ANALİZİ</b> (ID: <code>{fid}</code>)\n"
        f"🏆 <code>{lig}</code>\n"
        f"⚔️ <b>{ev} {ev_gol} - {dep_gol} {dep}</b>\n"
        f"📌 Durum: <b>{durum}</b>\n"
        f"-----------------------------------------\n"
        f"📈 <b>GÜNCEL BÜRO ORANLARI:</b>\n"
        f"🔹 2.5 Üst: <b>{ust25_o if ust25_o else 'Yok'}</b>\n"
        f"🔹 2.5 Alt: <b>{alt25_o if alt25_o else 'Yok'}</b>\n"
        f"🔹 KG Var: <b>{kg_var_o if kg_var_o else 'Yok'}</b>\n"
        f"-----------------------------------------\n"
        f"🎯 <b>SİSTEM TAHMİNİ:</b> <u>{tahmin_metni}</u>"
    )
    telegram_post(mesaj, chat_id)

def skorboard_getir(chat_id=None):
    target_chat = chat_id if chat_id else TELEGRAM_CHAT_ID
    db_veri, _ = github_db_oku()
    tahminler = db_veri.get("tahminler", {})

    if not tahminler:
        telegram_post("📊 Henüz tahmin yapılmış bir maç bulunmuyor.", target_chat)
        return

    tutan = sum(1 for v in tahminler.values() if v["durum"] == "✅ TUTTU")
    yatan = sum(1 for v in tahminler.values() if v["durum"] == "❌ GELMEDİ")
    bekleyen = sum(1 for v in tahminler.values() if "BEKLENİYOR" in v["durum"])
    basari_orani = round((tutan / (tutan + yatan)) * 100, 1) if (tutan + yatan) > 0 else 0

    satirlar = [
        "📊 <b>BUGÜNÜN TAHMİN SKORBOARDU</b>",
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

# ==========================================
# 4. SCHEDULER (Sadece Gece Sonu Raporu) & WEBHOOK
# ==========================================
scheduler = BackgroundScheduler()
# Sadece gece 23:59'da günün özet skorboard'unu gruba iletir
scheduler.add_job(func=lambda: skorboard_getir(TELEGRAM_CHAT_ID), trigger="cron", hour=23, minute=59)
scheduler.start()

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json()
    if update and "message" in update:
        message = update["message"]
        text = message.get("text", "").strip()
        chat_id = message["chat"]["id"]

        parcalar = text.split()
        komut = parcalar[0].lower() if parcalar else ""

        if komut in ["!skorboard", "!tahminler"]:
            threading.Thread(target=skorboard_getir, args=(chat_id,)).start()

        elif komut == "!kota":
            threading.Thread(target=manuel_kota_bilgisi_getir, args=(chat_id,)).start()

        elif komut == "!analiz":
            threading.Thread(target=analiz_getir, args=(parcalar[1:], chat_id)).start()

        elif komut in ["!bulten", "!maclar", "!bugun"]:
            threading.Thread(target=gunun_bulteni, args=(chat_id,)).start()

    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
