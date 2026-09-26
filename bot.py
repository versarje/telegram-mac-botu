import os
import random
import requests
from datetime import datetime, timedelta, timezone
import config
from db import execute_d1, init_d1_db

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
        return "00:00"

def rastgele_tahmin_uret():
    tahminler = [
        "⚽ MS 1", "⚽ MS 2", "🤝 MS X",
        "🔥 KG VAR", "🛡️ KG YOK",
        "🍿 2.5 ÜST", "🔒 2.5 ALT"
    ]
    return random.choice(tahminler)

def tahmin_kontrol_et(tahmin, ev_skor, dep_skor):
    if ev_skor is None or dep_skor is None or ev_skor < 0 or dep_skor < 0:
        return "⏳ Oynanmadı / Başlamadı"

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
                for sub_key in ["events", "matches", "data"]:
                    if sub_key in data[key] and isinstance(data[key][sub_key], list):
                        return data[key][sub_key]
    return []

# ==========================================
# 1. BÜLTENİ APİ'DEN ÇEKİP D1'E EKLE
# ==========================================

def bulteni_apiden_veritabanina_yukle(chat_id=None):
    init_d1_db()
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
        
        kalan_hak = res.headers.get("X-RateLimit-Requests-Remaining", "Bilinmiyor")
        toplam_hak = res.headers.get("X-RateLimit-Requests-Limit", "Bilinmiyor")
        
        events = []
        if res.status_code == 200:
            events = api_yanitindan_maclari_ayikla(res.json())

        if not events:
            kota_mesaji = f"\n\n📊 <b>Kalan API Hakkı:</b> {kalan_hak} / {toplam_hak}" if kalan_hak != "Bilinmiyor" else ""
            telegram_post(f"⚽ API'de bugün için maç bulunamadı.{kota_mesaji}", chat_id)
            return

        # MEVCUT MAÇLARI HIZLICA TEK SORGUDA HAFIZAYA ÇEKİYORUZ (Perf. Optimizasyonu)
        mevcut_maclar_raw = execute_d1("SELECT ev_sahibi, deplasman FROM maclar") or []
        mevcut_set = {(m['ev_sahibi'], m['deplasman']) for m in mevcut_maclar_raw}

        yeni_eklenen = 0

        for m in events:
            if not isinstance(m, dict):
                continue

            raw_ev = metin_veya_sozlukten_al(m.get("homeTeam"), "name") or m.get("homeTeamName") or "Ev Sahibi"
            raw_dep = metin_veya_sozlukten_al(m.get("awayTeam"), "name") or m.get("awayTeamName") or "Deplasman"
            ev = turkcelestir(raw_ev, tur="takim")
            dep = turkcelestir(raw_dep, tur="takim")

            if (ev, dep) in mevcut_set:
                continue

            startTimestamp = m.get("startTimestamp") or m.get("startTime") or m.get("time")
            saat = timestamp_saate_cevir(startTimestamp)

            raw_lig = metin_veya_sozlukten_al(m.get("tournament"), "name") or m.get("leagueName") or "Futbol"
            lig = turkcelestir(raw_lig, tur="lig")

            tahmin = rastgele_tahmin_uret()

            sql = "INSERT INTO maclar (saat, ev_sahibi, deplasman, lig, tahmin) VALUES (?, ?, ?, ?, ?)"
            execute_d1(sql, [saat, ev, dep, lig, tahmin])
            
            mevcut_set.add((ev, dep))
            yeni_eklenen += 1

        kota_bilgisi_str = f"\n💳 <b>Kalan API Kullanım Hakkı:</b> {kalan_hak} / {toplam_hak}" if kalan_hak != "Bilinmiyor" else ""
        telegram_post(
            f"✅ <b>Bülten Güncellendi!</b>\n"
            f"Yeni eklenen: <b>{yeni_eklenen}</b> maç."
            f"{kota_bilgisi_str}", 
            chat_id
        )

    except Exception as e:
        telegram_post(f"❌ İşlem Hatası: {e}", chat_id)

# ==========================================
# 2. DÜN VE BUGÜNÜN SKORLARINI D1'DE GÜNCELLE VE SKORLARI GETİR
# ==========================================

def biten_maclari_getir(chat_id=None):
    telegram_post("🔄 <b>Dün ve bugünün maç skorları kontrol ediliyor...</b>", chat_id)

    now_tr = get_turkey_now()
    bugun_str = now_tr.strftime("%Y-%m-%d")
    dun_str = (now_tr - timedelta(days=1)).strftime("%Y-%m-%d")
    
    headers = {
        "x-rapidapi-key": config.RAPIDAPI_KEY,
        "x-rapidapi-host": config.RAPIDAPI_HOST
    }

    for tarih_str in [dun_str, bugun_str]:
        url = f"{config.BASE_URL}/football-get-matches-by-date?date={tarih_str}"
        try:
            res = requests.get(url, headers=headers, timeout=20)
            if res.status_code == 200:
                events = api_yanitindan_maclari_ayikla(res.json())
                for m in events:
                    raw_ev = metin_veya_sozlukten_al(m.get("homeTeam"), "name") or "Ev Sahibi"
                    raw_dep = metin_veya_sozlukten_al(m.get("awayTeam"), "name") or "Deplasman"
                    ev = turkcelestir(raw_ev, tur="takim")
                    dep = turkcelestir(raw_dep, tur="takim")

                    home_score = m.get("homeScore", {}).get("current") if isinstance(m.get("homeScore"), dict) else None
                    away_score = m.get("awayScore", {}).get("current") if isinstance(m.get("awayScore"), dict) else None

                    if home_score is not None and away_score is not None:
                        update_sql = "UPDATE maclar SET ev_skor = ?, dep_skor = ? WHERE ev_sahibi = ? AND deplasman = ?"
                        execute_d1(update_sql, [home_score, away_score, ev, dep])
        except Exception as e:
            print(f"{tarih_str} skor çekme hatası: {e}")

    try:
        select_sql = "SELECT saat, ev_sahibi, deplasman, tahmin, ev_skor, dep_skor FROM maclar WHERE ev_skor IS NOT NULL AND ev_skor >= 0 ORDER BY saat ASC"
        bitenler = execute_d1(select_sql)

        if not bitenler:
            telegram_post("⏰ Henüz sonuçlanmış bir maç bulunamadı.", chat_id)
            return

        mesaj_blok = "🏆 <b>BİTEN MAÇLAR VE TAHMİN SONUÇLARI</b>\n-----------------------------------------\n"
        tutan_sayisi = 0

        for m in bitenler:
            durum = tahmin_kontrol_et(m['tahmin'], m['ev_skor'], m['dep_skor'])
            if "✅" in durum:
                tutan_sayisi += 1

            satir = (
                f"⏰ <b>{m['saat']}</b> | ⚔️ <b>{m['ev_sahibi']} {m['ev_skor']} - {m['dep_skor']} {m['deplasman']}</b>\n"
                f"🎯 Tahmin: <b>{m['tahmin']}</b> -> <b>{durum}</b>\n\n"
            )

            # Telegram 4096 karakter sınırına takılmamak için parçalı gönderim
            if len(mesaj_blok) + len(satir) > 3800:
                telegram_post(mesaj_blok, chat_id)
                mesaj_blok = ""

            mesaj_blok += satir

        mesaj_blok += f"-----------------------------------------\n📊 <b>Başarı Oranı: {tutan_sayisi} / {len(bitenler)} Maç Tuttu!</b>"
        telegram_post(mesaj_blok, chat_id)

    except Exception as e:
        telegram_post(f"❌ Sonuç getirme hatası: {e}", chat_id)
