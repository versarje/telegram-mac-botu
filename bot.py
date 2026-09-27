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

def get_paginated_matches_message(page=0, page_size=5):
    init_d1_db()
    offset = page * page_size
    maclar = execute_d1(f"SELECT * FROM maclar LIMIT {page_size} OFFSET {offset}") or []
    total_res = execute_d1("SELECT COUNT(*) as cnt FROM maclar")
    total = total_res[0]['cnt'] if total_res else 0
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    if not maclar:
        return "📊 Veritabanında kaydedilmiş oran analizi bulunamadı. Güncellemek için /güncelle yazabilirsiniz.", None

    mesaj = f"📊 <b>BAHİS ORAN ANALİZLERİ (Sayfa {page+1}/{total_pages})</b>\n\n"
    for m in maclar:
        ev = m.get("ev_sahibi", "Ev Sahibi")
        dep = m.get("deplasman", "Deplasman")
        saat = m.get("saat", "Canlı/Yakında")
        lig = m.get("lig", "Analiz")
        tahmin = m.get("tahmin", "Değerli Oran")
        
        mesaj += f"🏆 <b>{lig}</b>\n⏰ {saat} | {ev} vs {dep}\n💡 Fırsat/Analiz: <b>{tahmin}</b>\n-------------------\n"

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
    
    # Sportsbook API Oran Analizi (Odds Insights) Endpoint'i
    # type parametresi olarak PLUS_EV_AVERAGE veya ARBITRAGE kullanabiliriz[span_1](start_span)[span_1](end_span)
    analiz_turu = "PLUS_EV_AVERAGE" 
    url = f"{config.BASE_URL}/v0/advantages/?type={analiz_turu}"

    headers = {
        "x-rapidapi-key": config.RAPIDAPI_KEY,
        "x-rapidapi-host": config.RAPIDAPI_HOST
    }

    try:
        print(f"🔍 Oran analizi isteği atılıyor -> URL: {url}")
        res = requests.get(url, headers=headers, timeout=25)
        
        status_code = res.status_code
        raw_text = res.text[:400] # Debug için ilk 400 karakter
        
        # Debug bilgisini Telegram'a basalım ki dönen yapıyı net görebilelim
        debug_info = f"🛠 <b>ORAN API DEBUG</b>\n- Status Code: <b>{status_code}</b>\n- Yanıt Özeti: <pre>{raw_text}</pre>"
        telegram_post(debug_info, chat_id)

        if status_code != 200:
            telegram_post(f"❌ Oran API Hata Döndürdü! Kod: {status_code}", chat_id)
            return

        data = res.json()
        
        # Gelen veriyi liste veya sözlük yapısına göre ele alıyoruz
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("response", []) or data.get("data", []) or data.get("advantages", [])
            if not items and "result" in data:
                items = data["result"]

        if not items:
            telegram_post("⚠️ API'den analiz verisi döndü ancak liste boş veya farklı bir formatta.", chat_id)
            return

        yeni_eklenen = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            
            # Gelen yapıya göre takım ve oran bilgilerini ayıklıyoruz
            ev = item.get("homeTeam", "") or item.get("home", "Ev Sahibi")
            dep = item.get("awayTeam", "") or item.get("away", "Deplasman")
            lig = item.get("league", "") or item.get("sport", "Futbol Analiz")
            detay = item.get("description", "") or item.get("edge", "Değerli Oran Fırsatı")
            
            # Veritabanına kaydedelim
            execute_d1(
                "INSERT INTO maclar (saat, ev_sahibi, deplasman, lig, tahmin) VALUES (?, ?, ?, ?, ?)",
                ["Analiz", str(ev), str(dep), str(lig), str(detay)]
            )
            yeni_eklenen += 1

        telegram_post(f"✅ <b>Oran Analizleri Yüklendi!</b> ➕ <b>{yeni_eklenen}</b> yeni fırsat eklendi.", chat_id)
        msg, markup = get_paginated_matches_message(0)
        telegram_post(msg, chat_id, markup)

    except Exception as e:
        err_msg = f"❌ <b>Oran Analizi Kritik Hata:</b>\n<code>{str(e)}</code>"
        print(err_msg)
        telegram_post(err_msg, chat_id)

def yarin_bultenini_yukle(chat_id=None):
    bulteni_apiden_veritabanina_yukle(chat_id=chat_id)
