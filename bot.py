import os
import random
import requests
from datetime import datetime, timedelta, timezone
import config
from db import get_db_connection

TURKEY_TZ = timezone(timedelta(hours=3))

def get_turkey_now():
    return datetime.now(TURKEY_TZ)

def telegram_post(text, chat_id=None):
    target_chat_id = chat_id or config.TELEGRAM_CHAT_ID
    if not target_chat_id or not config.TELEGRAM_BOT_TOKEN:
        print("❌ Telegram token veya Chat ID eksik.")
        return

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": target_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"❌ Telegram gönderim hatası: {e}")

def metin_veya_sozlukten_al(veri, anahtar="name"):
    if isinstance(veri, dict):
        return veri.get(anahtar, "")
    elif isinstance(veri, str):
        return veri
    return ""

def turkcelestir(metin, tur="takim"):
    if not metin:
        return metin
    duzeltmeler = {
        " FC": "", " FK": "", " SK": "", " SC": "",
        "United": "Utd", "City": "City", "Real": "Real"
    }
    for k, v in duzeltmeler.items():
        metin = metin.replace(k, v)
    return metin.strip()

def timestamp_saate_cevir(ts):
    try:
        ts_int = int(ts)
        dt = datetime.fromtimestamp(ts_int, tz=timezone.utc).astimezone(TURKEY_TZ)
        return dt.strftime("%H:%M")
    except Exception:
        return "00:00"

def rastgele_tahmin_uret():
    tahminler = [
        "⚽ MS 1", "⚽ MS 2", "🤝 MS X",
        "🔥 KG VAR", "🛡️ KG YOK",
        "🍿 2.5 ÜST", "🔒 2.5 ALT"
    ]
    return random.choice(tahminler)

def api_yanitindan_maclari_ayikla(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ["response", "events", "data", "matches", "results"]:
            if key in data and isinstance(data[key], list):
                return data[key]
            elif key in data and isinstance(data[key], dict):
                for sub_key in ["events", "matches"]:
                    if sub_key in data[key] and isinstance(data[key][sub_key], list):
                        return data[key][sub_key]
    return []

# ==========================================
# 1. API'DEN BÜLTEN ÇEKİP VERİTABANINA YÜKLE
# ==========================================

def bulteni_apiden_veritabanina_yukle(chat_id=None):
    now_tr = get_turkey_now()
    bugun_tarih_str = now_tr.strftime("%Y-%m-%d")
    
    telegram_post(f"🔄 <b>{bugun_tarih_str} bülteni API'den çekiliyor...</b>", chat_id)

    headers = {
        "x-rapidapi-key": config.RAPIDAPI_KEY,
        "x-rapidapi-host": config.RAPIDAPI_HOST
    }
    
    url = f"{config.BASE_URL}/football-get-matches-by-date?date={bugun_tarih_str}"

    try:
        res = requests.get(url, headers=headers, timeout=25)
        events = []
        if res.status_code == 200:
            events = api_yanitindan_maclari_ayikla(res.json())
            
        if not events:
            alt_url = f"{config.BASE_URL}/football-get-matches-by-date?date={bugun_tarih_str.replace('-', '')}"
            res_alt = requests.get(alt_url, headers=headers, timeout=25)
            if res_alt.status_code == 200:
                events = api_yanitindan_maclari_ayikla(res_alt.json())

        if not events:
            telegram_post("⚽ API'de bugün için kaydedilecek maç bulunamadı.", chat_id)
            return

        tum_maclar = []
        ornek_saatler = []

        for m in events:
            if not isinstance(m, dict):
                continue

            raw_ev = metin_veya_sozlukten_al(m.get("homeTeam"), "name") or "Ev Sahibi"
            raw_dep = metin_veya_sozlukten_al(m.get("awayTeam"), "name") or "Deplasman"
            ev = turkcelestir(raw_ev, tur="takim")
            dep = turkcelestir(raw_dep, tur="takim")

            startTimestamp = m.get("startTimestamp")
            saat = timestamp_saate_cevir(startTimestamp) if startTimestamp else "00:00"

            if len(ornek_saatler) < 3:
                ornek_saatler.append(f"{saat} ({ev} vs {dep})")

            raw_lig = metin_veya_sozlukten_al(m.get("tournament"), "name") or "Futbol"
            lig = turkcelestir(raw_lig, tur="lig")

            tahmin = rastgele_tahmin_uret()

            tum_maclar.append({
                "saat": saat,
                "ev": ev,
                "dep": dep,
                "lig": lig,
                "tahmin": tahmin
            })

        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM maclar")
                    sql = """
                        INSERT INTO maclar (saat, ev_sahibi, deplasman, lig, tahmin)
                        VALUES (%s, %s, %s, %s, %s)
                    """
                    for m in tum_maclar:
                        cursor.execute(sql, (m["saat"], m["ev"], m["dep"], m["lig"], m["tahmin"]))
                conn.commit()
                
                ornek_metin = "\n".join(ornek_saatler)
                telegram_post(
                    f"✅ <b>Bülten Başarıyla Güncellendi!</b>\n"
                    f"Toplam <b>{len(tum_maclar)}</b> maç veritabanına yazıldı.\n\n"
                    f"📍 <b>Örnek Kaydedilen Saatler:</b>\n{ornek_metin}", 
                    chat_id
                )
            except Exception as db_err:
                telegram_post(f"❌ DB Kayıt Hatası: {db_err}", chat_id)
            finally:
                conn.close()
        else:
            telegram_post("❌ DB Bağlantısı kurulamadığı için veri yazılamadı!", chat_id)
    except Exception as e:
        telegram_post(f"❌ İşlem Hatası: {e}", chat_id)

# ==========================================
# 2. VERİTABANINDAN ÇEKİP TAHMİN SUNMA (/bbb)
# ==========================================

def veritabanindan_bulten_getir(chat_id=None, filtreli=True):
    now_tr = get_turkey_now()
    simdiki_saat = now_tr.strftime("%H:%M")
    
    conn = get_db_connection()
    if not conn:
        telegram_post("❌ Veritabanı bağlantısı kurulamadı.", chat_id)
        return

    try:
        with conn.cursor() as cursor:
            if filtreli:
                sql = "SELECT saat, ev_sahibi, deplasman, lig, tahmin FROM maclar WHERE saat >= %s ORDER BY saat ASC"
                cursor.execute(sql, (simdiki_saat,))
            else:
                # Saat filtresiz tüm maçları getirir (Test için)
                sql = "SELECT saat, ev_sahibi, deplasman, lig, tahmin FROM maclar ORDER BY saat ASC"
                cursor.execute(sql)

            maclar = cursor.fetchall()

        if not maclar:
            # Kaç tane toplam kayıt var kontrol et
            with conn.cursor() as cursor2:
                cursor2.execute("SELECT COUNT(*) as toplam FROM maclar")
                toplam_db = cursor2.fetchone().get("toplam", 0)

            telegram_post(
                f"⏰ <b>Sonuç Bulunamadı!</b>\n"
                f"Sorgu saati: <code>{simdiki_saat}</code>\n"
                f"DB'deki Toplam Maç Sayısı: <b>{toplam_db}</b>\n\n"
                f"<i>İpucu: Saat filtresiz bakmak için /bbb_all komutunu deneyin.</i>", 
                chat_id
            )
            return

        PARCA_BOYUTU = 15
        toplam_mac = len(maclar)
        toplam_sayfa = (toplam_mac + PARCA_BOYUTU - 1) // PARCA_BOYUTU

        for sayfa in range(min(toplam_sayfa, 3)):
            baslangic = sayfa * PARCA_BOYUTU
            bitis = baslangic + PARCA_BOYUTU
            sayfa_maclari = maclar[baslangic:bitis]

            mesaj_satirlari = [
                f"🎯 <b>GÜNÜN MAÇLARI VE TAHMİNLERİ</b>",
                f"📍 <i>Sayfa {sayfa + 1} / {min(toplam_sayfa, 3)} (Bulunan: {toplam_mac} Maç)</i>",
                "-----------------------------------------"
            ]

            for m in sayfa_maclari:
                mesaj_satirlari.append(
                    f"⏰ <b>{m['saat']}</b> | ⚔️ <b>{m['ev_sahibi']} vs {m['deplasman']}</b>\n"
                    f"🎯 Tahmin: <b>{m['tahmin']}</b> | 🏆 <i>{m['lig']}</i>\n"
                )

            mesaj_satirlari.append("-----------------------------------------")
            telegram_post("\n".join(mesaj_satirlari), chat_id)

    except Exception as e:
        telegram_post(f"❌ Veritabanı okuma hatası: {e}", chat_id)
    finally:
        conn.close()
