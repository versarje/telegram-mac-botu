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
        return veri.get(anahtar, "") or veri.get("shortName", "") or veri.get("longName", "")
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

def timestamp_saate_cevir(ts, time_str=None):
    if time_str and ":" in str(time_str):
        # Örn: "27.09.2026 18:00" -> "18:00"
        parcalar = str(time_str).split()
        if len(parcalar) >= 2 and ":" in parcalar[1]:
            return parcalar[1][:5]
            
    if not ts:
        return "00:00"
    try:
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
    if not isinstance(data, dict):
        return []
    
    # API yapısı: response -> matches dizisi
    response_obj = data.get("response", {})
    if isinstance(response_obj, dict):
        matches = response_obj.get("matches", [])
        if isinstance(matches, list):
            return matches
            
    matches_direct = data.get("matches", [])
    if isinstance(matches_direct, list):
        return matches_direct

    return []

def bulteni_apiden_veritabanina_yukle(chat_id=None, dt_obj=None):
    init_d1_db()
    
    if not dt_obj:
        dt_obj = get_turkey_now()
    
    api_date_str = dt_obj.strftime("%Y%m%d")
    gorunur_tarih = dt_obj.strftime("%Y-%m-%d")

    headers = {
        "x-rapidapi-key": config.RAPIDAPI_KEY,
        "x-rapidapi-host": config.RAPIDAPI_HOST
    }
    
    url = f"{config.BASE_URL}/football-get-matches-by-date?date={api_date_str}"

    try:
        res = requests.get(url, headers=headers, timeout=25)
        
        matches = []
        if res.status_code == 200:
            res_json = res.json()
            matches = api_yanitindan_maclari_ayikla(res_json)

        if not matches:
            telegram_post(f"⚠️ {gorunur_tarih} tarihi için maç bulunamadı veya API yanıtı boş.", chat_id)
            return

        mevcut_maclar_raw = execute_d1("SELECT ev_sahibi, deplasman FROM maclar") or []
        mevcut_set = {(m['ev_sahibi'], m['deplasman']) for m in mevcut_maclar_raw}

        yeni_eklenen = 0

        for m in matches:
            if not isinstance(m, dict):
                continue

            # API Yeni Obje Yapısı: home -> name / longName
            home_obj = m.get("home", {})
            away_obj = m.get("away", {})
            
            raw_ev = metin_veya_sozlukten_al(home_obj, "name") or metin_veya_sozlukten_al(home_obj, "longName") or "Ev Sahibi"
            raw_dep = metin_veya_sozlukten_al(away_obj, "name") or metin_veya_sozlukten_al(away_obj, "longName") or "Deplasman"
            
            ev = turkcelestir(raw_ev, tur="takim")
            dep = turkcelestir(raw_dep, tur="takim")

            if not ev or not dep or (ev, dep) in mevcut_set:
                continue

            # Saat bilgisini timeTS veya time stringinden alma
            time_str = m.get("time")
            time_ts = m.get("timeTS")
            saat = timestamp_saate_cevir(time_ts, time_str)

            # Lig Bilgisi
            tournament_obj = m.get("tournament", {})
            league_obj = m.get("league", {})
            raw_lig = (
                metin_veya_sozlukten_al(tournament_obj, "name") or 
                metin_veya_sozlukten_al(league_obj, "name") or 
                m.get("leagueName") or 
                "Futbol"
            )
            lig = turkcelestir(raw_lig, tur="lig")

            tahmin = rastgele_tahmin_uret()

            sql = "INSERT INTO maclar (saat, ev_sahibi, deplasman, lig, tahmin) VALUES (?, ?, ?, ?, ?)"
            execute_d1(sql, [saat, ev, dep, lig, tahmin])
            
            mevcut_set.add((ev, dep))
            yeni_eklenen += 1

        telegram_post(f"✅ <b>{gorunur_tarih}</b> bülteninden <b>{yeni_eklenen}</b> yeni maç veritabanına yüklendi!", chat_id)

    except Exception as e:
        telegram_post(f"❌ İşlem Hatası: {e}", chat_id)

def yarin_bultenini_yukle(chat_id=None):
    yarin_tr = get_turkey_now() + timedelta(days=1)
    bulteni_apiden_veritabanina_yukle(chat_id=chat_id, dt_obj=yarin_tr)

def biten_maclari_getir(chat_id=None):
    telegram_post("🔄 Biten maçlar kontrol ediliyor...", chat_id)
