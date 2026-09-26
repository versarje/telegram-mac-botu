import os
import random
import requests
from datetime import datetime, timedelta, timezone
import config
from db import execute_d1, init_d1_db

TURKEY_TZ = timezone(timedelta(hours=3))

def get_turkey_now():
    return datetime.now(TURKEY_TZ)

def telegram_post(text, chat_id=None, reply_markup=None):
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
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"❌ Telegram gönderim hatası: {e}")

def telegram_edit_message(chat_id, message_id, text, reply_markup=None):
    if not config.TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"❌ Telegram edit hatası: {e}")

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

def api_yanitindan_maclari_ayikla(data):
    if not isinstance(data, dict):
        return []
    
    response_obj = data.get("response", {})
    if isinstance(response_obj, dict):
        matches = response_obj.get("matches", [])
        if isinstance(matches, list):
            return matches
            
    matches_direct = data.get("matches", [])
    if isinstance(matches_direct, list):
        return matches_direct

    return []

def get_paginated_matches_message(page=0, page_size=5):
    init_d1_db()
    offset = page * page_size
    maclar = execute_d1(f"SELECT * FROM maclar LIMIT {page_size} OFFSET {offset}") or []
    total_res = execute_d1("SELECT COUNT(*) as cnt FROM maclar")
    total = total_res[0]['cnt'] if total_res else 0
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    if not maclar:
        return "📊 Veritabanında gösterilecek maç bulunamadı.", None

    mesaj = f"⚽ <b>BÜLTEN VE SKORLAR (Sayfa {page+1}/{total_pages})</b>\n\n"
    for m in maclar:
        ev = m.get("ev_sahibi", "")
        dep = m.get("deplasman", "")
        saat = m.get("saat", "00:00")
        lig = m.get("lig", "")
        tahmin = m.get("tahmin", "")
        ev_s = m.get("ev_skor")
        dep_s = m.get("dep_skor")
        
        skor_str = f" <b>[{ev_s} - {dep_s}]</b>" if ev_s is not None and dep_s is not None else " (Oynanmadı)"
        mesaj += f"🏆 <b>{lig}</b>\n⏰ {saat} | {ev} vs {dep}{skor_str}\n💡 Tahmin: <b>{tahmin}</b>\n-------------------\n"

    keyboard = {"inline_keyboard": []}
    row = []
    if page > 0:
        row.append({"text": "⬅️ Önceki", "callback_data": f"page_{page-1}"})
    if (page + 1) < total_pages:
        row.append({"text": "Sonraki ➡️", "callback_data": f"page_{page+1}"})
    if row:
        keyboard["inline_keyboard"].append(row)

    return mesaj, keyboard

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
        matches = api_yanitindan_maclari_ayikla(res.json()) if res.status_code == 200 else []

        if not matches:
            telegram_post(f"⚠️ {gorunur_tarih} tarihi için API'den maç gelmedi.", chat_id)
            return

        mevcut_maclar_raw = execute_d1("SELECT ev_sahibi, deplasman FROM maclar") or []
        mevcut_set = {(m['ev_sahibi'], m['deplasman']) for m in mevcut_maclar_raw}

        yeni_eklenen = 0
        for m in matches:
            if not isinstance(m, dict):
                continue
            home_obj = m.get("home", {})
            away_obj = m.get("away", {})
            
            ev = turkcelestir(metin_veya_sozlukten_al(home_obj, "name"), "takim")
            dep = turkcelestir(metin_veya_sozlukten_al(away_obj, "name"), "takim")

            if not ev or not dep:
                continue

            saat = timestamp_saate_cevir(m.get("timeTS"), m.get("time"))
            lig = turkcelestir(metin_veya_sozlukten_al(m.get("tournament", {}), "name") or "Futbol", "lig")

            if (ev, dep) not in mevcut_set:
                tahmin = rastgele_tahmin_uret()
                execute_d1(
                    "INSERT INTO maclar (saat, ev_sahibi, deplasman, lig, tahmin) VALUES (?, ?, ?, ?, ?)",
                    [saat, ev, dep, lig, tahmin]
                )
                mevcut_set.add((ev, dep))
                yeni_eklenen += 1

        telegram_post(f"✅ <b>{gorunur_tarih}</b> bülteni yüklendi: ➕ <b>{yeni_eklenen}</b> yeni maç eklendi.", chat_id)
        msg, markup = get_paginated_matches_message(0)
        telegram_post(msg, chat_id, markup)

    except Exception as e:
        telegram_post(f"❌ İşlem Hatası: {e}", chat_id)

def yarin_bultenini_yukle(chat_id=None):
    yarin_tr = get_turkey_now() + timedelta(days=1)
    bulteni_apiden_veritabanina_yukle(chat_id=chat_id, dt_obj=yarin_tr)

def canli_skorlari_guncelle_ve_getir(chat_id=None):
    init_d1_db()
    api_date_str = get_turkey_now().strftime("%Y%m%d")
    print(f"🔍 Livescores API'ye istek atılıyor, tarih: {api_date_str}")

    headers = {
        "x-rapidapi-key": config.RAPIDAPI_KEY,
        "x-rapidapi-host": config.RAPIDAPI_HOST
    }
    url = f"{config.BASE_URL}/football-get-livescores-by-date?date={api_date_str}"

    try:
        res = requests.get(url, headers=headers, timeout=25)
        print(f"📥 API Yanıt Kodu: {res.status_code}")
        
        if res.status_code == 200:
            data = res.json()
            matches = data.get("response", {}).get("live", [])
            if not matches and isinstance(data.get("response"), list):
                matches = data.get("response", [])
            
            print(f"⚽ API'den gelen canlı/biten maç sayısı: {len(matches)}")

            guncellenen = 0
            for m in matches:
                home_obj = m.get("home", {})
                away_obj = m.get("away", {})
                
                ev = turkcelestir(metin_veya_sozlukten_al(home_obj, "name"), "takim")
                dep = turkcelestir(metin_veya_sozlukten_al(away_obj, "name"), "takim")
                
                ev_skor = home_obj.get("score")
                dep_skor = away_obj.get("score")

                print(f"-> Kontrol ediliyor: {ev} vs {dep} | Skor: {ev_skor} - {dep_skor}")

                if ev_skor is not None and dep_skor is not None:
                    # Veritabanında bu maçı arayalım
                    sorgu = execute_d1(
                        "UPDATE maclar SET ev_skor = ?, dep_skor = ? WHERE ev_sahibi = ? AND deplasman = ?",
                        [ev_skor, dep_skor, ev, dep]
                    )
                    guncellenen += 1
            
            print(f"✅ Livescores güncellendi: Toplam {guncellenen} maç işlendi.")
        else:
            print(f"❌ API Hatası, içerik: {res.text}")
    except Exception as e:
        print(f"❌ Livescores API kritik hata: {e}")

    msg, markup = get_paginated_matches_message(0)
    telegram_post(msg, chat_id, markup)

