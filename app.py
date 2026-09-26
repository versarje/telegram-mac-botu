import os
import json
import random
import requests
import threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==========================================
# ⚙️ KONFİGÜRASYONLAR
# ==========================================
RAPIDAPI_KEY = "a218c708b2msh4439e269a1c67ebp1a33c8jsnb1f2b991cb2a"
RAPIDAPI_HOST = "free-api-live-football-data.p.rapidapi.com"
BASE_URL = f"https://{RAPIDAPI_HOST}"

TELEGRAM_BOT_TOKEN = "8894398415:AAEY_ffz8iPL8qZ8vJq3bgat7cibeQFhvI8"
TELEGRAM_CHAT_ID = "-1004461429503"

DB_FILE = "database.json"

# ==========================================
# 🔄 YEREL VERİTABANI İŞLEMLERİ
# ==========================================
def db_oku():
    if not os.path.exists(DB_FILE):
        veri = {"tahminler": {}}
        db_yaz(veri)
        return veri

    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "tahminler" not in data: data["tahminler"] = {}
            return data
    except Exception as e:
        print("❌ [DB OKUMA HATASI]:", e)
        return {"tahminler": {}}

def db_yaz(yeni_veri):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(yeni_veri, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print("❌ [DB YAZMA HATASI]:", e)
        return False

# ==========================================
# 1. TELEGRAM & API İSTEK FONKSİYONLARI
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

def api_request(endpoint, params=None):
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST
    }
    url = f"{BASE_URL}/{endpoint}"
    try:
        res = requests.get(url, headers=headers, params=params, timeout=20)
        if res.status_code == 200:
            return res.json()
        else:
            print(f"❌ API Hatası [{res.status_code}]: {res.text}")
            return None
    except Exception as e:
        print("❌ API İstek Hatası:", e)
        return None

def gunun_maclarini_cek():
    su_an_tsi = datetime.utcnow() + timedelta(hours=3)
    formatli_tarih = su_an_tsi.strftime("%Y%m%d")
    
    endpoint = "football-get-matches-by-date"
    res = api_request(endpoint, {"date": formatli_tarih})
    
    if not res:
        return []
        
    if isinstance(res, dict):
        if "response" in res and isinstance(res["response"], list):
            return res["response"]
        elif "status" in res and res["status"] == "success":
            data = res.get("response", res.get("data", {}))
            if isinstance(data, list): return data
            if isinstance(data, dict): return data.get("matches", data.get("events", []))
        elif "events" in res:
            return res["events"]
    elif isinstance(res, list):
        return res

    return []

# ==========================================
# 🔍 YERDEN VERİ AYIKLAMA YARDIMCISI (PARSER)
# ==========================================
def metin_veya_sozlukten_al(data, *anahtarlar):
    """Farklı JSON yapıları içinden doğru metni bulur."""
    if not data:
        return ""
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for key in anahtarlar:
            val = data.get(key)
            if val:
                if isinstance(val, str):
                    return val
                elif isinstance(val, dict):
                    res = val.get("name", val.get("text", ""))
                    if res: return str(res)
    return ""

# ==========================================
# 🎯 TAHMİN ALGORİTMASI
# ==========================================
def akilli_tahmin_uret(match_id, ev, dep):
    """
    Rastgelelik yerine maç id'si ve takim isimlerine bagli
    tutarlı ve belirli kurallara göre tahmin belirler.
    """
    TAHMINLER = [
        ("⚽ 2.5 ÜST", "UST25"),
        ("🛡️ 2.5 ALT", "ALT25"),
        ("🤝 KG VAR", "KG_VAR")
    ]
    
    # Isim uzunlukları ve ID ile tutarlı index üretimi
    seed = len(ev) + len(dep) + int("".join([c for c in str(match_id) if c.isdigit()] or "1"))
    indeks = seed % len(TAHMINLER)
    return TAHMINLER[indeks]

# ==========================================
# 2. RASTGELE / AKILLI TAHMİNLİ BÜLTEN (/bbb)
# ==========================================
def rastgele_bulten_tahmin_olustur(chat_id=None):
    su_an_tsi = datetime.utcnow() + timedelta(hours=3)
    tarih_gorunum = su_an_tsi.strftime("%Y-%m-%d")

    telegram_post("🔄 <b>Günün futbol bülteni çekiliyor...</b>", chat_id)

    events = gunun_maclarini_cek()
    
    if not events:
        telegram_post("📅 Bugün için bültende maç bulunamadı veya API bağlantısı kurulamadı.", chat_id)
        return

    db_veri = db_oku()

    mesaj_satirlari = [
        f"🎯 <b>GÜNÜN MAÇLARI VE TAHMİNLER ({tarih_gorunum})</b>",
        "-----------------------------------------"
    ]

    islenen_mac_sayisi = 0
    for m in events[:15]:
        fid = str(m.get("id", m.get("match_id", m.get("eventId", islenen_mac_sayisi))))
        
        # Derin JSON parse işlemleri
        lig = metin_veya_sozlukten_al(m.get("league"), "name") or \
              metin_veya_sozlukten_al(m.get("tournament"), "name") or "Futbol"

        ev = metin_veya_sozlukten_al(m.get("homeTeam"), "name") or \
             metin_veya_sozlukten_al(m.get("home_team"), "name") or \
             metin_veya_sozlukten_al(m.get("home"), "name") or "Ev Sahibi"

        dep = metin_veya_sozlukten_al(m.get("awayTeam"), "name") or \
              metin_veya_sozlukten_al(m.get("away_team"), "name") or \
              metin_veya_sozlukten_al(m.get("away"), "name") or "Deplasman"

        # Saat ayrıştırma
        time_val = m.get("time", m.get("start_time", ""))
        timestamp = m.get("startTimestamp", None)

        if timestamp and isinstance(timestamp, (int, float)):
            saat_tsi = (datetime.utcfromtimestamp(timestamp) + timedelta(hours=3)).strftime("%H:%M")
        elif time_val and ":" in str(time_val):
            # '26.09.2026 18:00' şeklinde geldiyse sadece saat kısmını al
            saat_parca = str(time_val).split()
            saat_tsi = saat_parca[-1] if len(saat_parca) > 1 else str(time_val)
        else:
            saat_tsi = "--:--"

        # Akıllı / Tutarlı Tahmin Belirleme
        secilen_tahmin_metin, secilen_tahmin_tur = akilli_tahmin_uret(fid, ev, dep)

        # Veritabanı kaydı
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
    mesaj_satirlari.append(f"💾 <i>{islenen_mac_sayisi} maç kaydedildi. Maçlar bitince /sonuc yazarak durumlarını kontrol edebilirsiniz.</i>")

    telegram_post("\n".join(mesaj_satirlari), chat_id)

# ==========================================
# 3. SONUÇ RAPORU VE KONTROL (/sonuc)
# ==========================================
def ayrintili_mac_sonuclarini_getir(chat_id=None):
    su_an_tsi = datetime.utcnow() + timedelta(hours=3)
    tarih_gorunum = su_an_tsi.strftime("%Y-%m-%d")

    events = gunun_maclarini_cek()
    if not events:
        telegram_post("🏁 Maç sonuçları taranırken API verisi alınamadı.", chat_id)
        return

    biten_maclar = {}
    for m in events:
        fid = str(m.get("id", m.get("match_id", m.get("eventId", ""))))
        status_val = m.get("status", {})
        if isinstance(status_val, dict):
            status = str(status_val.get("type", status_val.get("description", ""))).lower()
        else:
            status = str(status_val).lower()

        if status in ["finished", "ft", "ended", "100"]:
            biten_maclar[fid] = m

    db_veri = db_oku()
    tahminler = db_veri.get("tahminler", {})

    if not tahminler:
        telegram_post("📊 Henüz kaydedilmiş takip edilen bir maç yok.", chat_id)
        return

    degisiklik_var_mi = False

    for fid, t_data in tahminler.items():
        if fid in biten_maclar and t_data["durum"] == "⏳ BEKLENİYOR":
            m = biten_maclar[fid]
            
            home_score = m.get("homeScore", {}).get("current", m.get("scores", {}).get("home", 0))
            away_score = m.get("awayScore", {}).get("current", m.get("scores", {}).get("away", 0))
            
            try:
                home_score = int(home_score)
                away_score = int(away_score)
            except:
                home_score, away_score = 0, 0

            toplam_gol = home_score + away_score
            kg_var = (home_score > 0 and away_score > 0)

            tur = t_data["tur"]
            tuttu = False

            if tur == "UST25" and toplam_gol > 2: tuttu = True
            elif tur == "ALT25" and toplam_gol < 3: tuttu = True
            elif tur == "KG_VAR" and kg_var: tuttu = True

            t_data["skor"] = f"{home_score}-{away_score}"
            t_data["durum"] = "✅ TUTTU" if tuttu else "❌ GELMEDİ"
            degisiklik_var_mi = True

    if degisiklik_var_mi:
        db_yaz(db_veri)

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

    rapor = [f"📊 <b>GÜNÜN TAHMİN SONUÇ RAPORU ({tarih_gorunum})</b>\n"]

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
        rapor.append("⏳ <b>HENÜZ BİTMEYEN MAÇLAR</b>")
        rapor.append("-----------------------------------------")
        rapor.extend(bekleyenler[:5])
        rapor.append("")

    toplam_biten = len(tutanlar) + len(yatanlar)
    basari_yuzde = round((len(tutanlar) / toplam_biten) * 100, 1) if toplam_biten > 0 else 0
    rapor.append(f"📈 <b>Özet:</b> {len(tutanlar)} Tutan / {len(yatanlar)} Yatan | Başarı: <b>%{basari_yuzde}</b>")

    telegram_post("\n".join(rapor), chat_id)

# ==========================================
# 4. WEBHOOK & DINLEME
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

        if komut in ["/bbb", "/ototahmin"]:
            threading.Thread(target=rastgele_bulten_tahmin_olustur, args=(chat_id,)).start()

        elif komut in ["/sonuc", "/sonuclar", "/bitenler", "/rapor"]:
            threading.Thread(target=ayrintili_mac_sonuclarini_getir, args=(chat_id,)).start()

    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
