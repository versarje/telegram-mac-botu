import os
import time
import json
import random
import requests
import threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==========================================
# ⚙️ KONFİGÜRASYONLAR & AYARLAR
# ==========================================
API_KEYS = [
    "b699d9effa443321a65fd145ec78ede1",  # 1. API Key

]
CURRENT_KEY_INDEX = 0

BASE_URL = "https://v3.football.api-sports.io"
TELEGRAM_BOT_TOKEN = "8894398415:AAEY_ffz8iPL8qZ8vJq3bgat7cibeQFhvI8"
TELEGRAM_CHAT_ID = "-1004461429503"

# Yerel Veritabanı Dosyası
DB_FILE = "database.json"

KOTA_TAKIP = {
    "bugun_tarih": (datetime.utcnow() + timedelta(hours=3)).strftime("%Y-%m-%d"),
    "harcanan_istek": 0,
    "max_limit": 100 * len(API_KEYS)
}

# ==========================================
# 🔄 YEREL VERİTABANI OKUMA VE YAZMA SİSTEMİ
# ==========================================
def db_oku():
    if not os.path.exists(DB_FILE):
        veri = {"tahminler": {}, "bulten": {}}
        db_yaz(veri)
        return veri

    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "tahminler" not in data: data["tahminler"] = {}
            if "bulten" not in data: data["bulten"] = {}
            return data
    except Exception as e:
        print("❌ [DB OKUMA HATASI]:", e)
        return {"tahminler": {}, "bulten": {}}

def db_yaz(yeni_veri):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(yeni_veri, f, ensure_ascii=False, indent=2)
        print("✅ Yerel database.json başarıyla güncellendi!")
        return True
    except Exception as e:
        print("❌ [DB YAZMA HATASI]:", e)
        return False

# ==========================================
# 1. YARDIMCI FONKSİYONLAR & API GEÇİŞİ
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

def api_request(endpoint, params=None, chat_id=None):
    global CURRENT_KEY_INDEX, KOTA_TAKIP
    bugun = (datetime.utcnow() + timedelta(hours=3)).strftime("%Y-%m-%d")
    
    if KOTA_TAKIP["bugun_tarih"] != bugun:
        KOTA_TAKIP["bugun_tarih"] = bugun
        KOTA_TAKIP["harcanan_istek"] = 0
        CURRENT_KEY_INDEX = 0

    deneme_sayisi = 0
    toplam_key = len(API_KEYS)

    while deneme_sayisi < toplam_key:
        active_key = API_KEYS[CURRENT_KEY_INDEX].strip()
        headers = {
            "x-apisports-key": active_key,
            "Accept": "application/json"
        }

        url = f"{BASE_URL}/{endpoint}"
        try:
            res = requests.get(url, params=params, headers=headers, timeout=30)
            res_json = res.json()

            errors = res_json.get("errors", {})

            is_rate_limit = False
            if isinstance(errors, dict):
                if "requests" in errors or "rateLimit" in errors:
                    is_rate_limit = True
                elif errors:
                    print(f"❌ API HATASI (Key {CURRENT_KEY_INDEX + 1}): {errors}")

            if is_rate_limit or res.status_code == 429:
                CURRENT_KEY_INDEX = (CURRENT_KEY_INDEX + 1) % toplam_key
                deneme_sayisi += 1
                continue

            if res_json.get("response") is not None:
                KOTA_TAKIP["harcanan_istek"] += 1
                return res_json
            else:
                CURRENT_KEY_INDEX = (CURRENT_KEY_INDEX + 1) % toplam_key
                deneme_sayisi += 1

        except Exception as e:
            print(f"❌ [API BAGLANTI HATASI - Key {CURRENT_KEY_INDEX + 1}]:", e)
            CURRENT_KEY_INDEX = (CURRENT_KEY_INDEX + 1) % toplam_key
            deneme_sayisi += 1

    telegram_post("⚠️ <b>TÜM API KEY'LERİN KOTASI DOLDU VEYA HATA ALINDI!</b>", chat_id)
    return None

# ==========================================
# 2. RASTGELE TAHMİNLİ BÜLTEN OLUSTURMA (/bbb)
# ==========================================
def rastgele_bulten_tahmin_olustur(chat_id=None):
    su_an_tsi = datetime.utcnow() + timedelta(hours=3)
    tarih_str = su_an_tsi.strftime("%Y-%m-%d")

    telegram_post("🔄 <b>Günün bülteni çekiliyor ve yapay tahminler oluşturuluyor...</b>", chat_id)

    res_data = api_request("fixtures", {"date": tarih_str, "timezone": "Europe/Istanbul"}, chat_id=chat_id)
    if not res_data or not res_data.get("response"):
        telegram_post("📅 Bugün için bültende maç bulunamadı veya API hatası oluştu.", chat_id)
        return

    data = res_data.get("response", [])
    gelecek_maclar = [m for m in data if m["fixture"]["status"]["short"] == "NS"]

    if not gelecek_maclar:
        telegram_post("📅 Bugün oynanacak başka maç kalmadı.", chat_id)
        return

    gelecek_maclar.sort(key=lambda m: m["fixture"]["date"])

    # Rastgele Seçilebilecek Tahmin Havuzu
    TAHMIN_HAVUZU = [
        ("⚽ 2.5 ÜST", "UST25"),
        ("🛡️ 2.5 ALT", "ALT25"),
        ("🤝 KG VAR", "KG_VAR")
    ]

    db_veri = db_oku()
    if "tahminler" not in db_veri: db_veri["tahminler"] = {}

    mesaj_satirlari = [
        f"🎯 <b>GÜNÜN MAÇLARI VE OTOMATİK TAHMİNLER ({tarih_str})</b>",
        "-----------------------------------------"
    ]

    islenen_mac_sayisi = 0
    for m in gelecek_maclar[:15]:  # Mesaj sınırı için ilk 15 maç
        fid = str(m["fixture"]["id"])
        lig = m["league"]["name"]
        ev = m["teams"]["home"]["name"]
        dep = m["teams"]["away"]["name"]

        mac_zamani_raw = m["fixture"]["date"]
        try:
            dt_utc = datetime.fromisoformat(mac_zamani_raw.replace('Z', '+00:00'))
            dt_tsi = dt_utc + timedelta(hours=3)
            saat_tsi = dt_tsi.strftime("%H:%M")
        except:
            saat_tsi = mac_zamani_raw[11:16]

        # Rastgele tahmin seçimi
        secilen_tahmin_metin, secilen_tahmin_tur = random.choice(TAHMIN_HAVUZU)

        # Veritabanına kaydet
        db_veri["tahminler"][fid] = {
            "mac": f"{ev} vs {dep}",
            "lig": lig,
            "saat": saat_tsi,
            "tahmin": secilen_tahmin_metin,
            "tur": secilen_tahmin_tur,
            "skor": "0-0",
            "durum": "⏳ BEKLENİYOR"
        }

        mesaj_satirlari.append(
            f"⏰ <b>{saat_tsi}</b> | 🏆 <i>{lig}</i>\n"
            f"⚔️ <b>{ev} vs {dep}</b>\n"
            f"🎯 Tahmin: <b>{secilen_tahmin_metin}</b>\n"
        )
        islenen_mac_sayisi += 1

    db_yaz(db_veri)

    mesaj_satirlari.append("-----------------------------------------")
    mesaj_satirlari.append(f"💾 <i>{islenen_mac_sayisi} maç veritabanına kaydedildi. Maçlar bittiğinde /sonuc yazarak tutan/tutmama durumunu görebilirsiniz.</i>")

    telegram_post("\n".join(mesaj_satirlari), chat_id)

# ==========================================
# 3. AYRI LİSTELİ SONUÇ RAPORU (/sonuc)
# ==========================================
def ayrintili_mac_sonuclarini_getir(chat_id=None):
    su_an_tsi = datetime.utcnow() + timedelta(hours=3)
    tarih_str = su_an_tsi.strftime("%Y-%m-%d")

    res_data = api_request("fixtures", {"date": tarih_str, "timezone": "Europe/Istanbul"}, chat_id=chat_id)
    if not res_data or not res_data.get("response"):
        telegram_post("🏁 Biten maçlar taranırken API verisi alınamadı.", chat_id)
        return

    data = res_data.get("response", [])
    biten_maclar = {str(m["fixture"]["id"]): m for m in data if m["fixture"]["status"]["short"] in ['FT', 'AET', 'PEN']}

    db_veri = db_oku()
    tahminler = db_veri.get("tahminler", {})

    if not tahminler:
        telegram_post("📊 Henüz veritabanında takip edilen bir maç yok.", chat_id)
        return

    degisiklik_var_mi = False

    # Maç sonuçlarını güncelle
    for fid, t_data in tahminler.items():
        if fid in biten_maclar and t_data["durum"] == "⏳ BEKLENİYOR":
            m = biten_maclar[fid]
            ev_gol = m["goals"]["home"] if m["goals"]["home"] is not None else 0
            dep_gol = m["goals"]["away"] if m["goals"]["away"] is not None else 0
            toplam_gol = ev_gol + dep_gol
            kg_var = (ev_gol > 0 and dep_gol > 0)

            tur = t_data["tur"]
            tuttu = False

            if tur == "UST25" and toplam_gol > 2: tuttu = True
            elif tur == "ALT25" and toplam_gol < 3: tuttu = True
            elif tur == "KG_VAR" and kg_var: tuttu = True

            t_data["skor"] = f"{ev_gol}-{dep_gol}"
            t_data["durum"] = "✅ TUTTU" if tuttu else "❌ GELMEDİ"
            degisiklik_var_mi = True

    if degisiklik_var_mi:
        db_yaz(db_veri)

    # Tutan ve Tutmayanları Ayrıştır
    tutanlar = []
    yatanlar = []
    bekleyenler = []

    for fid, t in tahminler.items():
        metin = f"🔹 <b>{t['mac']}</b> ({t['skor']})\n🎯 Tahmin: <i>{t['tahmin']}</i>"
        if t["durum"] == "✅ TUTTU":
            tutanlar.append(metin)
        elif t["durum"] == "❌ GELMEDİ":
            yatanlar.append(metin)
        else:
            bekleyenler.append(f"⏳ <b>{t['mac']}</b> - <i>{t['tahmin']}</i>")

    # Rapor Mesajını Oluştur
    rapor = [f"📊 <b>GÜNÜN TAHMİN SONUÇ RAPORU ({tarih_str})</b>\n"]

    if tutanlar:
        rapor.append("✅ <b>TUTAN TAHMİNLER</b>")
        rapor.append("-----------------------------------------")
        rapor.extend(tutanlar)
        rapor.append("")

    if yatanlar:
        rapor.append("❌ <b>TUTMAYAN TAHMİNLER</b>")
        rapor.append("-----------------------------------------")
        rapor.extend(yatanlar)
        rapor.append("")

    if bekleyenler:
        rapor.append("⏳ <b>HENÜZ BİTMEYEN / BEKLEYEN MAÇLAR</b>")
        rapor.append("-----------------------------------------")
        rapor.extend(bekleyenler[:5])
        rapor.append("")

    toplam_biten = len(tutanlar) + len(yatanlar)
    basari_yuzde = round((len(tutanlar) / toplam_biten) * 100, 1) if toplam_biten > 0 else 0
    rapor.append(f"📈 <b>Özet:</b> {len(tutanlar)} Tutan / {len(yatanlar)} Yatan | Başarı: <b>%{basari_yuzde}</b>")

    telegram_post("\n".join(rapor), chat_id)

# ==========================================
# 4. FLASK WEBHOOK & KOMUT DİNLENMESİ
# ==========================================
@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json()
    if update and "message" in update:
        message = update["message"]
        text = message.get("text", "").strip()
        chat_id = message["chat"]["id"]

        parcalar = text.split()
        komut = parcalar[0].lower() if parcalar else ""

        # YENİ KOMUT: /bbb
        if komut in ["/bbb", "/ototahmin"]:
            threading.Thread(target=rastgele_bulten_tahmin_olustur, args=(chat_id,)).start()

        elif komut in ["/sonuc", "/sonuclar", "/bitenler", "/rapor"]:
            threading.Thread(target=ayrintili_mac_sonuclarini_getir, args=(chat_id,)).start()

    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
