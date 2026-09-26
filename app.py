import os
import re
import random
import requests
import threading
import pymysql
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==========================================
# ⚙️ KONFİGÜRASYONLAR (RAPIDAPI & TELEGRAM)
# ==========================================
RAPIDAPI_KEY = "a218c708b2msh4439e269a1c67ebp1a33c8jsnb1f2b991cb2a"
RAPIDAPI_HOST = "free-api-live-football-data.p.rapidapi.com"
BASE_URL = f"https://{RAPIDAPI_HOST}"

TELEGRAM_BOT_TOKEN = "8894398415:AAEY_ffz8iPL8qZ8vJq3bgat7cibeQFhvI8"
TELEGRAM_CHAT_ID = "-1004461429503"

# ==========================================
# 🗄️ AIVEN MYSQL VERİTABANI BAĞLANTISI
# ==========================================
MYSQL_HOST = "mysql-2d07f53d-umuttopal51-ec18.e.aivencloud.com"
MYSQL_PORT = 21611
MYSQL_USER = "avnadmin"
MYSQL_PASSWORD = "AVNS_H5i1d0aVTmZE1CfZZrQ"
MYSQL_DB = "defaultdb"

# ==========================================
# 🔤 TÜRKÇELEŞTİRME SÖZLÜKLERİ
# ==========================================
LIG_SOZLUK = {
    "Premier League": "İngiltere Premier Lig",
    "LaLiga": "İspanya La Liga",
    "Serie A": "İtalya Serie A",
    "Bundesliga": "Almanya Bundesliga",
    "Ligue 1": "Fransa Ligue 1",
    "Super Lig": "Trendyol Süper Lig",
    "Eredivisie": "Hollanda Eredivisie",
    "Primeira Liga": "Portekiz Süper Ligi",
    "UEFA Champions League": "UEFA Şampiyonlar Ligi",
    "UEFA Europa League": "UEFA Avrupa Ligi",
    "UEFA Conference League": "UEFA Konferans Ligi",
    "Championship": "İngiltere Championship"
}

TAKIM_SOZLUK = {
    "Bayern München": "Bayern Münih",
    "Bayern Munich": "Bayern Münih",
    "Red Star Belgrade": "Kızılıldız",
    "Sporting CP": "Sporting Lizbon",
    "Athletic Club": "Athletic Bilbao",
    "Inter": "Inter Milan",
    "AC Milan": "Milan",
    "PSV Eindhoven": "PSV",
    "AZ Alkmaar": "AZ Alkmaar",
    "Köln": "Köln",
    "Nürnberg": "Nürnberg"
}

def turkcelestir(metin, tur="takim"):
    if not metin:
        return "Bilinmiyor"
    
    # Sözlük kontrolü
    sozluk = LIG_SOZLUK if tur == "lig" else TAKIM_SOZLUK
    for eng, tr in sozluk.items():
        if eng.lower() in metin.lower():
            return tr
            
    if tur == "takim":
        # Takım isimlerindeki genel ekleri temizleme
        metin = re.sub(r'\b(FC|CF|BSC|FK|SK|SV|AC|SC)\b', '', metin, flags=re.IGNORECASE).strip()
        
    return metin

def db_baglan():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        db=MYSQL_DB,
        charset="utf8mb4",
        connect_timeout=10,
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor
    )

def tablo_kur():
    try:
        conn = db_baglan()
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tahminler (
                    match_id VARCHAR(50) PRIMARY KEY,
                    mac VARCHAR(150),
                    lig VARCHAR(100),
                    saat VARCHAR(20),
                    tahmin VARCHAR(50),
                    tur VARCHAR(20),
                    skor VARCHAR(20) DEFAULT '0-0',
                    durum VARCHAR(50) DEFAULT '⏳ BEKLENİYOR',
                    tarih VARCHAR(20)
                );
            """)
        conn.close()
        print("✅ MySQL Tablosu Hazır.")
    except Exception as e:
        print("❌ [MYSQL TABLO HATA]:", e)

tablo_kur()

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

def metin_veya_sozlukten_al(data, *anahtarlar):
    if not data: return ""
    if isinstance(data, str): return data
    if isinstance(data, dict):
        for key in anahtarlar:
            val = data.get(key)
            if val:
                if isinstance(val, str): return val
                elif isinstance(val, dict):
                    res = val.get("name", val.get("text", ""))
                    if res: return str(res)
    return ""

def akilli_tahmin_uret(match_id, ev, dep):
    TAHMINLER = [
        ("⚽ 2.5 ÜST", "UST25"),
        ("🛡️ 2.5 ALT", "ALT25"),
        ("🤝 KG VAR", "KG_VAR")
    ]
    seed = len(ev) + len(dep) + int("".join([c for c in str(match_id) if c.isdigit()] or "1"))
    indeks = seed % len(TAHMINLER)
    return TAHMINLER[indeks]

# ==========================================
# 2. TÜRKÇELEŞTİRİLMİŞ BÜLTEN (/bbb)
# ==========================================
def rastgele_bulten_tahmin_olustur(chat_id=None):
    su_an_tsi = datetime.utcnow() + timedelta(hours=3)
    tarih_gorunum = su_an_tsi.strftime("%Y-%m-%d")

    telegram_post("🔄 <b>Günün futbol bülteni çekiliyor...</b>", chat_id)

    events = gunun_maclarini_cek()
    
    if not events:
        telegram_post("📅 Bugün için bültende maç bulunamadı veya API bağlantısı kurulamadı.", chat_id)
        return

    mesaj_satirlari = [
        f"🎯 <b>GÜNÜN MAÇLARI VE TAHMİNLER ({tarih_gorunum})</b>",
        "-----------------------------------------"
    ]

    islenen_mac_sayisi = 0
    conn = db_baglan()

    try:
        with conn.cursor() as cursor:
            for m in events[:15]:
                fid = str(m.get("id", m.get("match_id", m.get("eventId", islenen_mac_sayisi))))
                
                raw_lig = metin_veya_sozlukten_al(m.get("league"), "name") or \
                          metin_veya_sozlukten_al(m.get("tournament"), "name") or "Futbol"

                raw_ev = metin_veya_sozlukten_al(m.get("homeTeam"), "name") or \
                         metin_veya_sozlukten_al(m.get("home_team"), "name") or \
                         metin_veya_sozlukten_al(m.get("home"), "name") or "Ev Sahibi"

                raw_dep = metin_veya_sozlukten_al(m.get("awayTeam"), "name") or \
                          metin_veya_sozlukten_al(m.get("away_team"), "name") or \
                          metin_veya_sozlukten_al(m.get("away"), "name") or "Deplasman"

                # Türkçe Dönüşümleri
                lig = turkcelestir(raw_lig, tur="lig")
                ev = turkcelestir(raw_ev, tur="takim")
                dep = turkcelestir(raw_dep, tur="takim")

                time_val = m.get("time", m.get("start_time", ""))
                timestamp = m.get("startTimestamp", None)

                if timestamp and isinstance(timestamp, (int, float)):
                    saat_tsi = (datetime.utcfromtimestamp(timestamp) + timedelta(hours=3)).strftime("%H:%M")
                elif time_val and ":" in str(time_val):
                    saat_parca = str(time_val).split()
                    saat_tsi = saat_parca[-1] if len(saat_parca) > 1 else str(time_val)
                else:
                    saat_tsi = "--:--"

                secilen_tahmin_metin, secilen_tahmin_tur = akilli_tahmin_uret(fid, ev, dep)
                mac_adi = f"{ev} vs {dep}"

                sql = """
                    INSERT INTO tahminler (match_id, mac, lig, saat, tahmin, tur, tarih)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE mac=%s, saat=%s, tarih=%s;
                """
                cursor.execute(sql, (fid, mac_adi, lig, saat_tsi, secilen_tahmin_metin, secilen_tahmin_tur, tarih_gorunum, mac_adi, saat_tsi, tarih_gorunum))

                mesaj_satirlari.append(
                    f"⏰ <b>{saat_tsi}</b> | 🏆 <i>{lig}</i>\n"
                    f"⚔️ <b>{ev} vs {dep}</b>\n"
                    f"🎯 Tahmin: <b>{secilen_tahmin_metin}</b>\n"
                )
                islenen_mac_sayisi += 1
    finally:
        conn.close()

    mesaj_satirlari.append("-----------------------------------------")
    mesaj_satirlari.append(f"💾 <i>{islenen_mac_sayisi} maç kaydedildi. Maçlar bitince /sonuc yazabilirsiniz.</i>")

    telegram_post("\n".join(mesaj_satirlari), chat_id)

# ==========================================
# 3. MYSQL SONUÇ RAPORU (/sonuc)
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

    conn = db_baglan()
    tahminler = []
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM tahminler WHERE durum = '⏳ BEKLENİYOR'")
            bekleyenler_db = cursor.fetchall()

            for t_data in bekleyenler_db:
                fid = t_data["match_id"]
                if fid in biten_maclar:
                    m = biten_maclar[fid]
                    home_score = m.get("homeScore", {}).get("current", m.get("scores", {}).get("home", 0))
                    away_score = m.get("awayScore", {}).get("current", m.get("scores", {}).get("away", 0))

                    try:
                        home_score, away_score = int(home_score), int(away_score)
                    except:
                        home_score, away_score = 0, 0

                    toplam_gol = home_score + away_score
                    kg_var = (home_score > 0 and away_score > 0)
                    tur = t_data["tur"]
                    tuttu = False

                    if tur == "UST25" and toplam_gol > 2: tuttu = True
                    elif tur == "ALT25" and toplam_gol < 3: tuttu = True
                    elif tur == "KG_VAR" and kg_var: tuttu = True

                    yeni_skor = f"{home_score}-{away_score}"
                    yeni_durum = "✅ TUTTU" if tuttu else "❌ GELMEDİ"

                    cursor.execute("UPDATE tahminler SET skor = %s, durum = %s WHERE match_id = %s", (yeni_skor, yeni_durum, fid))

            cursor.execute("SELECT * FROM tahminler WHERE tarih = %s", (tarih_gorunum,))
            tahminler = cursor.fetchall()
    finally:
        conn.close()

    if not tahminler:
        telegram_post("📊 Henüz bugün için kaydedilmiş maç yok.", chat_id)
        return

    tutanlar, yatanlar, bekleyenler = [], [], []

    for t in tahminler:
        metin = f"🔹 <b>{t['mac']}</b> ({t['skor']})\n🎯 Tahmin: <i>{t['tahmin']}</i>"
        if t["durum"] == "✅ TUTTU": tutanlar.append(metin)
        elif t["durum"] == "❌ GELMEDİ": yatanlar.append(metin)
        else: bekleyenler.append(f"⏳ <b>{t['mac']}</b> - <i>{t['tahmin']}</i>")

    rapor = [f"📊 <b>GÜNÜN TAHMİN SONUÇ RAPORU ({tarih_gorunum})</b>\n"]

    if tutanlar:
        rapor.append("✅ <b>TUTAN TAHMİNLER</b>\n" + "-----------------------------------------")
        rapor.extend(tutanlar)
        rapor.append("")

    if yatanlar:
        rapor.append("❌ <b>TUTMAYAN TAHMİNLER</b>\n" + "-----------------------------------------")
        rapor.extend(yatanlar)
        rapor.append("")

    if bekleyenler:
        rapor.append("⏳ <b>HENÜZ BİTMEYEN MAÇLAR</b>\n" + "-----------------------------------------")
        rapor.extend(bekleyenler[:5])
        rapor.append("")

    toplam_biten = len(tutanlar) + len(yatanlar)
    basari_yuzde = round((len(tutanlar) / toplam_biten) * 100, 1) if toplam_biten > 0 else 0
    rapor.append(f"📈 <b>Özet:</b> {len(tutanlar)} Tutan / {len(yatanlar)} Yatan | Başarı: <b>%{basari_yuzde}</b>")

    telegram_post("\n".join(rapor), chat_id)

# ==========================================
# 4. WEBHOOK & LİSTEN
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
