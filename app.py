import os
import json
import random
import requests
import threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==========================================
# ⚙️ KONFİGÜRASYONLAR & SOFASCORE API
# ==========================================
RAPIDAPI_KEY = "A218c708b2msh4439e269a1c67ebp1a33c8jsnb1f2b991cb2a"
RAPIDAPI_HOST = "sofascore.p.rapidapi.com"
BASE_URL = "https://sofascore.p.rapidapi.com"

TELEGRAM_BOT_TOKEN = "8894398415:AAEY_ffz8iPL8qZ8vJq3bgat7cibeQFhvI8"
TELEGRAM_CHAT_ID = "-1004461429503"

DB_FILE = "database.json"

# ==========================================
# 🔄 YEREL VERİTABANI OKUMA VE YAZMA SİSTEMİ
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

# ==========================================
# 2. RASTGELE TAHMİNLİ BÜLTEN (/bbb)
# ==========================================
def rastgele_bulten_tahmin_olustur(chat_id=None):
    su_an_tsi = datetime.utcnow() + timedelta(hours=3)
    tarih_str = su_an_tsi.strftime("%Y-%m-%d")

    telegram_post("🔄 <b>Sofascore üzerinden günün bülteni çekiliyor...</b>", chat_id)

    # Sofascore günün maçları uç noktası
    res_data = api_request("events/get-by-date", {"date": tarih_str, "sport": "football"})
    
    if not res_data or "events" not in res_data:
        telegram_post("📅 Bugün için Sofascore üzerinde maç bulunamadı veya API hatası alındı.", chat_id)
        return

    events = res_data.get("events", [])
    
    # Henüz başlamamış maçlar (status.type == 'notstarted')
    gelecek_maclar = [m for m in events if m.get("status", {}).get("type") == "notstarted"]

    if not gelecek_maclar:
        telegram_post("📅 Bugün oynanacak başlamamış maç kalmadı.", chat_id)
        return

    TAHMIN_HAVUZU = [
        ("⚽ 2.5 ÜST", "UST25"),
        ("🛡️ 2.5 ALT", "ALT25"),
        ("🤝 KG VAR", "KG_VAR")
    ]

    db_veri = db_oku()

    mesaj_satirlari = [
        f"🎯 <b>GÜNÜN SOFASCORE MAÇLARI VE TAHMİNLER ({tarih_str})</b>",
        "-----------------------------------------"
    ]

    islenen_mac_sayisi = 0
    for m in gelecek_maclar[:15]:  # Mesaj uzunluk sınırı için ilk 15 maç
        fid = str(m.get("id"))
        lig = m.get("tournament", {}).get("name", "Futbol")
        ev = m.get("homeTeam", {}).get("name", "Ev")
        dep = m.get("awayTeam", {}).get("name", "Deplasman")

        timestamp = m.get("startTimestamp")
        if timestamp:
            saat_tsi = (datetime.utcfromtimestamp(timestamp) + timedelta(hours=3)).strftime("%H:%M")
        else:
            saat_tsi = "--:--"

        secilen_tahmin_metin, secilen_tahmin_tur = random.choice(TAHMIN_HAVUZU)

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
    mesaj_satirlari.append(f"💾 <i>{islenen_mac_sayisi} maç kaydedildi. Maçlar bitince /sonuc yazarak durumlarını görebilirsiniz.</i>")

    telegram_post("\n".join(mesaj_satirlari), chat_id)

# ==========================================
# 3. SONUÇ RAPORU (/sonuc)
# ==========================================
def ayrintili_mac_sonuclarini_getir(chat_id=None):
    su_an_tsi = datetime.utcnow() + timedelta(hours=3)
    tarih_str = su_an_tsi.strftime("%Y-%m-%d")

    res_data = api_request("events/get-by-date", {"date": tarih_str, "sport": "football"})
    if not res_data or "events" not in res_data:
        telegram_post("🏁 Maç sonuçları taranırken API verisi alınamadı.", chat_id)
        return

    events = res_data.get("events", [])
    biten_maclar = {str(m["id"]): m for m in events if m.get("status", {}).get("type") == "finished"}

    db_veri = db_oku()
    tahminler = db_veri.get("tahminler", {})

    if not tahminler:
        telegram_post("📊 Henüz kaydedilmiş takip edilen bir maç yok.", chat_id)
        return

    degisiklik_var_mi = False

    for fid, t_data in tahminler.items():
        if fid in biten_maclar and t_data["durum"] == "⏳ BEKLENİYOR":
            m = biten_maclar[fid]
            home_score = m.get("homeScore", {}).get("current", 0)
            away_score = m.get("awayScore", {}).get("current", 0)
            
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
