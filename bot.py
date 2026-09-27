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
        telegram_post("🔍 Oran analizi API'den çekiliyor, CSV raporu hazırlanıyor...", chat_id)
        
        res = requests.get(url, headers=headers, timeout=25)
        status_code = res.status_code
        
        if status_code != 200:
            telegram_post(f"❌ Oran API Hata Döndürdü! Kod: {status_code}", chat_id)
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

        # Doğrudan CSV dosyası oluştur
        filename = f"Bahis_Analizleri_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        with open(filename, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["ID", "Zaman", "Ev Sahibi / Maç", "Deplasman / Pazar", "Kategori", "Tahmin / Detay"])
            
            for idx, item in enumerate(items[:300], start=1): # İlk 300 temiz veri
                if not isinstance(item, dict):
                    continue
                
                val_type = item.get("type", "ANALIZ")
                val_oran = item.get("value", 0)
                market = item.get("marketKey", "Genel Pazar")
                event_id = item.get("eventKey", "Bilinmeyen")
                
                lig = f"Tür: {val_type}"
                ev = f"Maç ID: {event_id[:12]}" if event_id else "Maç"
                dep = f"Pazar: {market[:12]}" if market else "Pazar"
                detay = f"Değer: {val_oran}"

                writer.writerow([idx, "Analiz", ev, dep, lig, detay])

        print(f"✅ CSV dosyası başarıyla oluşturuldu: {filename}")
        caption = f"📈 <b>Güncel Bahis Fırsatları Raporu</b>\nAPI'den anlık çekilen <b>{min(len(items), 300)}</b> analiz doğrudan CSV olarak aktarıldı."
        
        telegram_send_document(filename, caption, chat_id)

        # Geçici dosyayı temizle
        try:
            os.remove(filename)
        except:
            pass

    except Exception as e:
        err_msg = f"❌ <b>Veri İşleme Kritik Hatası:</b>\n<code>{str(e)}</code>"
        print(err_msg)
        telegram_post(err_msg, chat_id)

def yarin_bultenini_yukle(chat_id=None):
    bulteni_apiden_veritabanina_yukle(chat_id=chat_id)
