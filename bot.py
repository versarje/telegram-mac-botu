import os
import csv
import json
import requests
from datetime import datetime, timedelta, timezone
import config

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

def telegram_send_document(file_path, caption="", chat_id=None):
    target_chat_id = chat_id or config.TELEGRAM_CHAT_ID
    if not target_chat_id or not config.TELEGRAM_BOT_TOKEN:
        print("❌ Telegram Chat ID veya Token eksik, dosya gönderilemiyor.")
        return

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendDocument"
    try:
        with open(file_path, "rb") as f:
            files = {"document": f}
            data = {"chat_id": target_chat_id, "caption": caption, "parse_mode": "HTML"}
            res = requests.post(url, data=data, files=files, timeout=30)
            print(f"📁 Dosya gönderim yanıtı: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"❌ Telegram dosya gönderim hatası: {e}")

def bulteni_apiden_veritabanina_yukle(chat_id=None, dt_obj=None):
    headers = {
        "x-rapidapi-key": config.RAPIDAPI_KEY,
        "x-rapidapi-host": config.RAPIDAPI_HOST
    }

    try:
        telegram_post("🔍 Oranlar ve maç detayları API'den alınıyor...", chat_id)
        
        # 1. Adım: Avantajları (Arbitrage / +EV) çekelim
        advantages_url = f"{config.BASE_URL}/v1/advantages/"
        res = requests.get(advantages_url, headers=headers, timeout=25)
        if res.status_code != 200:
            telegram_post(f"❌ Oran API Hata Döndürdü! Kod: {res.status_code}", chat_id)
            return

        data = res.json()
        items = []
        if isinstance(data, dict):
            advantages_obj = data.get("advantages", {})
            if isinstance(advantages_obj, dict):
                for key in ["ARBITRAGE", "PLUS_EV_AVERAGE", "PLUS_EV_PINNACLE"]:
                    val = advantages_obj.get(key)
                    if isinstance(val, list):
                        items.extend(val)
                if not items:
                    for key, val in advantages_obj.items():
                        if isinstance(val, list):
                            items.extend(val)
            elif isinstance(advantages_obj, list):
                items = advantages_obj
        elif isinstance(data, list):
            items = data

        if not items:
            telegram_post("⚠️ API'den yanıt alındı ancak uygun içerik bulunamadı.", chat_id)
            return

        # 2. Adım: items içindeki eventKey'leri toplayalım (En fazla 100 adet alalım ki API sınırına takılmayalım)
        event_keys = []
        for item in items[:100]:
            if isinstance(item, dict):
                ek = item.get("eventKey")
                if ek and ek not in event_keys:
                    event_keys.append(ek)

        # 3. Adım: /v0/events/ uç noktasına eventKeys parametresi ile toplu istek atalım[span_1](start_span)[span_1](end_span)
        events_map = {}
        if event_keys:
            events_url = f"{config.BASE_URL}/v0/events/"
            params = {
                "eventKeys": json.dumps(event_keys),
                "returnType": "array"
            }
            try:
                ev_res = requests.get(events_url, headers=headers, params=params, timeout=20)
                if ev_res.status_code == 200:
                    ev_data = ev_res.json()
                    ev_list = ev_data if isinstance(ev_data, list) else ev_data.get("events", [])
                    for ev in ev_list:
                        if isinstance(ev, dict):
                            e_key = str(ev.get("key", ev.get("id", "")))
                            home = ev.get("homeTeam", ev.get("home", ""))
                            away = ev.get("awayTeam", ev.get("away", ""))
                            name = ev.get("name", ev.get("eventName", ""))
                            if not name and home and away:
                                name = f"{home} - {away}"
                            
                            league = ev.get("leagueName", ev.get("league", ev.get("tournament", "Genel Lig")))
                            if e_key:
                                events_map[e_key] = {
                                    "name": name or f"Etkinlik {e_key}",
                                    "league": league
                                }
            except Exception as ex:
                print(f"⚠️ Toplu maç detayları çekilemedi: {ex}")

        # 4. Adım: CSV raporunu oluşturalım
        filename = f"Bahis_Analizleri_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        with open(filename, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["ID", "Tür", "Maç / Takımlar", "Lig", "Oran / Değer", "Bahis Büroları ve Oranlar"])
            
            for idx, item in enumerate(items[:100], start=1):
                if not isinstance(item, dict):
                    continue
                
                val_type = item.get("type", "ANALIZ")
                val_oran = item.get("value", 0)
                event_key = str(item.get("eventKey", ""))
                
                # Eşleşen maç adını ve ligi alalım
                match_info = events_map.get(event_key, {})
                match_name = match_info.get("name")
                league_name = match_info.get("league")

                # Eğer eşleşmezse item içindekilere bakalım
                if not match_name:
                    match_name = item.get("eventName") or item.get("name") or item.get("matchName") or f"Maç ID: {event_key[:8] if event_key else 'Bilinmeyen'}"
                
                if not league_name:
                    league_name = item.get("leagueName") or item.get("league") or "Genel"

                # Bahis büroları ve oranlar
                outcomes = item.get("outcomes", [])
                siteler = []
                if isinstance(outcomes, list):
                    for out in outcomes:
                        if isinstance(out, dict):
                            src = out.get("source", "Büro")
                            payout = out.get("payout", out.get("odds", 0))
                            try:
                                payout_formatted = f"{float(payout):.2f}"
                            except:
                                payout_formatted = str(payout)
                            siteler.append(f"{src}: {payout_formatted}")
                
                detay_siteler = " | ".join(siteler) if siteler else "Oran detayı yok"

                writer.writerow([idx, val_type, match_name, league_name, val_oran, detay_siteler])

        print(f"✅ CSV dosyası oluşturuldu: {filename}")
        caption = f"📈 <b>Gerçek Maç İsimli Analiz Raporu</b>\n<b>{min(len(items), 100)}</b> adet analiz takımları ve ligleriyle birlikte raporlandı."
        
        telegram_send_document(filename, caption, chat_id)

        try:
            os.remove(filename)
        except:
            pass

    except Exception as e:
        err_msg = f"❌ <b>Hata:</b>\n<code>{str(e)}</code>"
        print(err_msg)
        telegram_post(err_msg, chat_id)

def yarin_bultenini_yukle(chat_id=None):
    bulteni_apiden_veritabanina_yukle(chat_id=chat_id)
