import os
import csv
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

def telegram_send_document(file_path, caption="", chat_id=None):
    target_chat_id = chat_id or config.TELEGRAM_CHAT_ID
    if not target_chat_id or not config.TELEGRAM_BOT_TOKEN:
        return

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendDocument"
    try:
        with open(file_path, "rb") as f:
            files = {"document": f}
            data = {"chat_id": target_chat_id, "caption": caption, "parse_mode": "HTML"}
            requests.post(url, data=data, files=files, timeout=30)
    except Exception as e:
        print(f"❌ Telegram dosya gönderim hatası: {e}")

def csv_dosyasi_olustur_ve_gonder(chat_id=None):
    init_d1_db()
    maclar = execute_d1("SELECT * FROM maclar") or []

    if not maclar:
        telegram_post("📊 Veritabanında dışa aktarılacak veri bulunamadı.", chat_id)
        return

    # Excel ile uyumlu (UTF-8 BOM destekli) CSV dosyası oluşturma
    filename = f"Bahis_Analizleri_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    try:
        with open(filename, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            # Başlıklar
            writer.writerow(["ID", "Zaman", "Ev Sahibi / Maç", "Deplasman / Pazar", "Kategori", "Tahmin / Detay"])
            
            # Veriler
            for idx, m in enumerate(maclar, start=1):
                writer.writerow([
                    m.get("id", idx),
                    m.get("saat", "Analiz"),
                    m.get("ev_sahibi", ""),
                    m.get("deplasman", ""),
                    m.get("lig", ""),
                    m.get("tahmin", "")
                ])
    except Exception as e:
        print(f"❌ CSV yazma hatası: {e}")
        return

    caption = f"📈 <b>Güncel Bahis Fırsatları Raporu</b>\nToplam <b>{len(maclar)}</b> analiz CSV (Excel uyumlu) olarak dışa aktarıldı."
    telegram_send_document(filename, caption, chat_id)

    # Geçici dosyayı temizle
    try:
        os.remove(filename)
    except:
        pass

def bulteni_apiden_veritabanina_yukle(chat_id=None, dt_obj=None):
    init_d1_db()
    
    url = f"{config.BASE_URL}/v1/advantages/"

    headers = {
        "x-rapidapi-key": config.RAPIDAPI_KEY,
        "x-rapidapi-host": config.RAPIDAPI_HOST
    }

    try:
        print(f"🔍 Oran analizi isteği atılıyor -> URL: {url}")
        res = requests.get(url, headers=headers, timeout=25)
        
        status_code = res.status_code
        raw_text = res.text[:400]
        
        debug_info = f"🛠 <b>ORAN API DEBUG</b>\n- Status Code: <b>{status_code}</b>\n- Yanıt Özeti: <pre>{raw_text}</pre>"
        telegram_post(debug_info, chat_id)

        if status_code != 200:
            telegram_post(f"❌ Oran API Hata Döndürdü! Kod: {status_code}", chat_id)
            return

        data = res.json()
        
        # Ekran görüntüsündeki JSON yapısına göre advantages altındaki tüm listeleri topluyoruz
        items = []
        if isinstance(data, dict):
            advantages_obj = data.get("advantages", {})
            if isinstance(advantages_obj, dict):
                for key, val in advantages_obj.items():
                    if isinstance(val, list):
                        items.extend(val)
            elif isinstance(advantages_obj, list):
                items = advantages_obj
        elif isinstance(data, list):
            items = data

        if not items:
            telegram_post("⚠️ API'den yanıt alındı ancak avantaj içeriği boş.", chat_id)
            return

        yeni_eklenen = 0
        for item in items:
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

            execute_d1(
                "INSERT INTO maclar (saat, ev_sahibi, deplasman, lig, tahmin) VALUES (?, ?, ?, ?, ?)",
                ["Analiz", str(ev), str(dep), str(lig), str(detay)]
            )
            yeni_eklenen += 1

        telegram_post(f"✅ <b>Analizler İşlendi!</b> ➕ <b>{yeni_eklenen}</b> kayıt veritabanına eklendi. Tablo raporu hazırlanıyor...", chat_id)
        
        # Dosyayı oluşturup Telegram'a gönder
        csv_dosyasi_olustur_ve_gonder(chat_id)

    except Exception as e:
        err_msg = f"❌ <b>Veri İşleme Kritik Hatası:</b>\n<code>{str(e)}</code>"
        print(err_msg)
        telegram_post(err_msg, chat_id)

def yarin_bultenini_yukle(chat_id=None):
    bulteni_apiden_veritabanina_yukle(chat_id=chat_id)
