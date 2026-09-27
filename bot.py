import os
import csv
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
    url = f"{config.BASE_URL}/v1/advantages/"
    headers = {
        "x-rapidapi-key": config.RAPIDAPI_KEY,
        "x-rapidapi-host": config.RAPIDAPI_HOST
    }

    try:
        print(f"🔍 Oran analizi isteği atılıyor -> URL: {url}")
        telegram_post("🔍 Oranlar API'den çekiliyor, oranlar ve kaynaklar CSV'ye işleniyor...", chat_id)
        
        res = requests.get(url, headers=headers, timeout=25)
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

        print(f"📦 İşlenecek toplam item sayısı: {len(items)}")

        if not items:
            telegram_post("⚠️ API'den yanıt alındı ancak uygun içerik bulunamadı.", chat_id)
            return

        filename = f"Bahis_Analizleri_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        with open(filename, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            # Sütun başlıklarını gerçek verilere göre anlamlı hale getirdik
            writer.writerow(["ID", "Fırsat Türü", "Genel Değer / %", "Market / Pazar ID", "Bahis Sitesi 1 (Kaynak & Oran)", "Bahis Sitesi 2 (Kaynak & Oran)"])
            
            for idx, item in enumerate(items[:300], start=1):
                if not isinstance(item, dict):
                    continue
                
                val_type = item.get("type", "ANALIZ")
                val_oran = item.get("value", 0)
                market = item.get("marketKey", "-")
                
                # Outcoming içindeki bahis sitelerini ve oranları (payout) ayıklıyoruz
                outcomes = item.get("outcomes", [])
                siteler = []
                if isinstance(outcomes, list):
                    for out in outcomes:
                        if isinstance(out, dict):
                            src = out.get("source", "Bilinmeyen")
                            payout = out.get("payout", 0)
                            try:
                                payout_formatted = f"{float(payout):.2f}"
                            except:
                                payout_formatted = str(payout)
                            siteler.append(f"{src}: {payout_formatted}")
                
                site1 = siteler[0] if len(siteler) > 0 else "-"
                site2 = siteler[1] if len(siteler) > 1 else "-"

                writer.writerow([idx, val_type, val_oran, market, site1, site2])

        print(f"✅ CSV dosyası başarıyla oluşturuldu: {filename}")
        caption = f"📈 <b>Güncel Bahis Fırsatları Raporu</b>\nAPI'den çekilen <b>{min(len(items), 300)}</b> oran analizi detaylı olarak CSV'ye aktarıldı."
        
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
