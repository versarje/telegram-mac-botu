import os
import random
import requests
from datetime import datetime, timedelta, timezone
import config
from db import get_db_connection

# Türkiye Saati (UTC+3)
TURKEY_TZ = timezone(timedelta(hours=3))

def get_turkey_now():
    """Türkiye yerel saatini döndürür."""
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
        return veri.get(anahtar, "") or veri.get("shortName", "") or veri.get("nameCode", "")
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
    """
    API'den gelen Unix Timestamp (UTC) veya String saat bilgisini 
    Türkiye saatine (+3 saat) çevirip HH:MM formatında verir.
    """
    if not ts:
        return "00:00"
    
    try:
        if isinstance(ts, str) and ":" in ts:
            parcalar = ts.split(":")
            if len(parcalar) >= 2:
                return f"{parcalar[0].zfill(2)}:{parcalar[1].zfill(2)}"

        ts_int = int(ts)
        if ts_int > 100000000000:
            ts_int = ts_int // 1000

        dt = datetime.fromtimestamp(ts_int, tz=timezone.utc).astimezone(TURKEY_TZ)
        return dt.strftime("%H:%M")
    except Exception as e:
        print(f"Saat dönüştürme hatası ({ts}): {e}")
        return "00:00"

def rastgele_tahmin_uret():
    tahminler = [
        "⚽ MS 1", "⚽ MS 2", "🤝 MS X",
        "🔥 KG VAR", "🛡️ KG YOK",
        "🍿 2.5 ÜST", "🔒 2.5 ALT"
    ]
    return random.choice(tahminler)

def tahmin_kontrol_et(tahmin, ev_skor, dep_skor):
    """Biten maç skoruna göre tahminin durumunu belirler."""
    if ev_skor is None or dep_skor is None or ev_skor < 0 or dep_skor < 0:
        return "⏳ Devam Ediyor / Başlamadı"

    toplam_gol = ev_skor + dep_skor
    
    if "MS 1" in tahmin:
        return "✅ TUTTU" if ev_skor > dep_skor else "❌ TUTMADI"
    elif "MS 2" in tahmin:
        return "✅ TUTTU" if dep_skor > ev_skor else "❌ TUTMADI"
    elif "MS X" in tahmin:
        return "✅ TUTTU" if ev_skor == dep_skor else "❌ TUTMADI"
    elif "KG VAR" in tahmin:
        return "✅ TUTTU" if (ev_skor > 0 and dep_skor > 0) else "❌ TUTMADI"
    elif "KG YOK" in tahmin:
        return "✅ TUTTU" if (ev_skor == 0 or dep_skor == 0) else "❌ TUTMADI"
    elif "2.5 ÜST" in tahmin:
        return "✅ TUTTU" if toplam_gol > 2.5 else "❌ TUTMADI"
    elif "2.5 ALT" in tahmin:
        return "✅ TUTTU" if toplam_gol < 2.5 else "❌ TUTMADI"
    
    return "❓ Belirsiz"

def api_yanitindan_maclari_ayikla(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ["events", "response", "data", "matches", "results"]:
            if key in data and isinstance(data[key], list):
                return data[key]
            elif key in data and isinstance(data[key], dict):
                for sub_key in ["events", "matches"]:
                    if sub_key in data[key] and isinstance(data[key][sub_key], list):
                        return data[key][sub_key]
    return []

# ==========================================
# 1. API'DEN BÜLTEN ÇEKİP VERİTABANINA YÜKLE + KOTA BİLGİSİ
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
        
        # RapidAPI Kota Bilgilerini Header'dan Çek
        kalan_hak = res.headers.get("X-RateLimit-Requests-Remaining", "Bilinmiyor")
        toplam_hak = res.headers.get("X-RateLimit-Requests-Limit", "Bilinmiyor")
        
        events = []
        if res.status_code == 200:
            events = api_yanitindan_maclari_ayikla(res.json())
            
        if not events:
            alt_url = f"{config.BASE_URL}/football-get-matches-by-date?date={bugun_tarih_str.replace('-', '')}"
            res_alt = requests.get(alt_url, headers=headers, timeout=25)
            # Alt istek olursa kota bilgisini güncelle
            kalan_hak = res_alt.headers.get("X-RateLimit-Requests-Remaining", kalan_hak)
            toplam_hak = res_alt.headers.get("X-RateLimit-Requests-Limit", toplam_hak)
            if res_alt.status_code == 200:
                events = api_yanitindan_maclari_ayikla(res_alt.json())

        if not events:
            kota_mesajı = f"\n\n📊 <b>Kalan API Hakkı:</b> {kalan_hak} / {toplam_hak}" if kalan_hak != "Bilinmiyor" else ""
            telegram_post(f"⚽ API'de bugün için kaydedilecek maç bulunamadı.{kota_mesajı}", chat_id)
            return

        tum_maclar = []
        for m in events:
            if not isinstance(m, dict):
                continue

            raw_ev = (
                metin_veya_sozlukten_al(m.get("homeTeam"), "name") or 
                metin_veya_sozlukten_al(m.get("home"), "name") or 
                m.get("homeTeamName") or "Ev Sahibi"
            )
            raw_dep = (
                metin_veya_sozlukten_al(m.get("awayTeam"), "name") or 
                metin_veya_sozlukten_al(m.get("away"), "name") or 
                m.get("awayTeamName") or "Deplasman"
            )
            ev = turkcelestir(raw_ev, tur="takim")
            dep = turkcelestir(raw_dep, tur="takim")

            startTimestamp = (
                m.get("startTimestamp") or 
                m.get("startTimestampMs") or 
                m.get("startTime") or 
                m.get("time") or 
                m.get("formatedStarttime") or
                (m.get("status", {}).get("startTimestamp") if isinstance(m.get("status"), dict) else None)
            )
            saat = timestamp_saate_cevir(startTimestamp)

            raw_lig = (
                metin_veya_sozlukten_al(m.get("tournament"), "name") or 
                metin_veya_sozlukten_al(m.get("category"), "name") or
                metin_veya_sozlukten_al(m.get("league"), "name") or 
                m.get("leagueName") or "Futbol"
            )
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
                cursor = conn.cursor()
                cursor.execute("DELETE FROM maclar")
                sql = """
                    INSERT INTO maclar (saat, ev_sahibi, deplasman, lig, tahmin)
                    VALUES (?, ?, ?, ?, ?)
                """
                for m in tum_maclar:
                    cursor.execute(sql, (m["saat"], m["ev"], m["dep"], m["lig"], m["tahmin"]))
                
                conn.commit()
                
                # Başarı mesajına kalan kota bilgisini ekliyoruz
                kota_bilgisi_str = f"\n💳 <b>Kalan API Kullanım Hakkı:</b> {kalan_hak} / {toplam_hak}" if kalan_hak != "Bilinmiyor" else ""
                
                telegram_post(
                    f"✅ <b>Bülten Başarıyla Güncellendi!</b>\n"
                    f"Toplam <b>{len(tum_maclar)}</b> maç veritabanına kaydedildi."
                    f"{kota_bilgisi_str}", 
                    chat_id
                )
            except Exception as db_err:
                telegram_post(f"❌ DB Kayıt Hatası: {db_err}", chat_id)
            finally:
                conn.close()
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
        cursor = conn.cursor()
        if filtreli:
            sql = """
                SELECT saat, ev_sahibi, deplasman, lig, tahmin 
                FROM maclar 
                WHERE saat >= ? 
                ORDER BY saat ASC
            """
            cursor.execute(sql, (simdiki_saat,))
        else:
            sql = """
                SELECT saat, ev_sahibi, deplasman, lig, tahmin 
                FROM maclar 
                ORDER BY saat ASC
            """
            cursor.execute(sql)

        maclar = cursor.fetchall()

        if not maclar:
            telegram_post(
                f"⏰ Bugün saat {simdiki_saat} sonrası için kayıtlı maç kalmadı veya veritabanı boş.\n"
                f"Tüm maçları görmek için <b>/bbb_all</b> yapın ya da bülteni <b>/guncelle</b> yapın.", 
                chat_id
            )
            return

        PARCA_BOYUTU = 15
        toplam_mac = len(maclar)
        toplam_sayfa = (toplam_mac + PARCA_BOYUTU - 1) // PARCA_BOYUTU

        baslik_ek = f"(Saat {simdiki_saat} Sonrası)" if filtreli else "(Tüm Maçlar)"

        for sayfa in range(min(toplam_sayfa, 3)):
            baslangic = sayfa * PARCA_BOYUTU
            bitis = baslangic + PARCA_BOYUTU
            sayfa_maclari = maclar[baslangic:bitis]

            mesaj_satirlari = [
                f"🎯 <b>GÜNÜN MAÇLARI VE TAHMİNLERİ</b>",
                f"📍 <i>Sayfa {sayfa + 1} / {min(toplam_sayfa, 3)} {baslik_ek}</i>",
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
        telegram_post(f"❌ DB Okuma Hatası: {e}", chat_id)
    finally:
        conn.close()

# ==========================================
# 3. BİTEN MAÇLARIN SKORLARINI VE SONUÇLARINI GETİR (/sonuclar)
# ==========================================

def biten_maclari_getir(chat_id=None):
    telegram_post("🔄 <b>Günün skorları çekiliyor ve tahminler kontrol ediliyor...</b>", chat_id)

    now_tr = get_turkey_now()
    bugun_tarih_str = now_tr.strftime("%Y-%m-%d")
    
    headers = {
        "x-rapidapi-key": config.RAPIDAPI_KEY,
        "x-rapidapi-host": config.RAPIDAPI_HOST
    }
    url = f"{config.BASE_URL}/football-get-matches-by-date?date={bugun_tarih_str}"

    try:
        res = requests.get(url, headers=headers, timeout=25)
        if res.status_code == 200:
            events = api_yanitindan_maclari_ayikla(res.json())
            
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                for m in events:
                    raw_ev = metin_veya_sozlukten_al(m.get("homeTeam"), "name") or "Ev Sahibi"
                    raw_dep = metin_veya_sozlukten_al(m.get("awayTeam"), "name") or "Deplasman"
                    ev = turkcelestir(raw_ev, tur="takim")
                    dep = turkcelestir(raw_dep, tur="takim")

                    home_score = m.get("homeScore", {}).get("current") if isinstance(m.get("homeScore"), dict) else None
                    away_score = m.get("awayScore", {}).get("current") if isinstance(m.get("awayScore"), dict) else None

                    if home_score is not None and away_score is not None:
                        cursor.execute(
                            "UPDATE maclar SET ev_skor = ?, dep_skor = ? WHERE ev_sahibi = ? AND deplasman = ?",
                            (home_score, away_score, ev, dep)
                        )
                conn.commit()
                conn.close()
    except Exception as e:
        print(f"Skor güncelleme hatası: {e}")

    conn = get_db_connection()
    if not conn:
        telegram_post("❌ Veritabanı bağlantısı kurulamadı.", chat_id)
        return

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT saat, ev_sahibi, deplasman, tahmin, ev_skor, dep_skor FROM maclar WHERE ev_skor >= 0 ORDER BY saat ASC")
        bitenler = cursor.fetchall()

        if not bitenler:
            telegram_post("⏰ Henüz sonuçlanmış veya skoru girilmiş bir maç bulunamadı.", chat_id)
            return

        mesaj_satirlari = [
            "🏆 <b>BITEN MAÇLAR VE TAHMİN SONUÇLARI</b>",
            "-----------------------------------------"
        ]

        tutan_sayisi = 0
        for m in bitenler:
            durum = tahmin_kontrol_et(m['tahmin'], m['ev_skor'], m['dep_skor'])
            if "✅" in durum:
                tutan_sayisi += 1

            mesaj_satirlari.append(
                f"⏰ <b>{m['saat']}</b> | ⚔️ <b>{m['ev_sahibi']} {m['ev_skor']} - {m['dep_skor']} {m['deplasman']}</b>\n"
                f"🎯 Tahmin: <b>{m['tahmin']}</b> -> <b>{durum}</b>\n"
            )

        mesaj_satirlari.append("-----------------------------------------")
        mesaj_satirlari.append(f"📊 <b>Başarı Oranı: {tutan_sayisi} / {len(bitenler)} Maç Tuttu!</b>")

        telegram_post("\n".join(mesaj_satirlari), chat_id)

    except Exception as e:
        telegram_post(f"❌ Sonuç getirme hatası: {e}", chat_id)
    finally:
        conn.close()
