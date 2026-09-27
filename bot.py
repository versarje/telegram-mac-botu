import requests
import datetime
import pytz
import config

# --- ZAMAN VE YARDIMCI FONKSİYONLAR ---

def get_turkey_now():
    turkey_tz = pytz.timezone('Europe/Istanbul')
    return datetime.datetime.now(turkey_tz)

def turkcelestir(metin, tip="genel"):
    if not metin:
        return ""
    # Gerekli Türkçe karakter veya isim düzeltmeleri buraya eklenebilir
    return metin.strip()

def metin_veya_sozlukten_al(veri, anahtar):
    if isinstance(veri, dict):
        return veri.get(anahtar, "")
    return str(veri)

def telegram_post(text, chat_id=None, reply_markup=None):
    if not chat_id:
        chat_id = getattr(config, 'TELEGRAM_CHAT_ID', None)
    if not chat_id:
        print("❌ Telegram chat_id bulunamadı!")
        return
        
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
        
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram mesajı gönderilemedi: {e}")

# --- VERİTABANI İŞLEMLERİ (Örnek Fonksiyonlar) ---

def init_d1_db():
    # Veritabanı tablo oluşturma ve bağlantı işlemleri burada yer alır
    pass

def execute_d1(query, params=None):
    # Veritabanı sorgu çalıştırma fonksiyonu
    pass

def get_paginated_matches_message(page=0):
    # Sayfalandırılmış maç listesi mesajını ve buton markup'ını döndürür
    return "⚽ **Günün Maçları Bülteni**", None


# --- GÜNCELLENEN BÜLTEN FONKSİYONU ---

def bulteni_apiden_veritabanina_yukle(chat_id=None):
    init_d1_db()
    
    # Bugünün tarihini YYYYMMDD formatında alıyoruz
    api_date_str = get_turkey_now().strftime("%Y%m%d")

    headers = {
        "x-rapidapi-key": config.RAPIDAPI_KEY,
        "x-rapidapi-host": config.RAPIDAPI_HOST
    }
    
    # Kararlı ve çalışan maç bülteni endpoint'i
    url = f"{config.BASE_URL}/football-get-matches-by-date?date={api_date_str}"

    try:
        res = requests.get(url, headers=headers, timeout=25)
        if res.status_code == 200:
            data = res.json()
            
            # API'den gelen bülten verilerini işleme
            matches = data.get("response", [])
            if isinstance(matches, dict):
                matches = matches.get("matches", [])

            kaydedilen = 0
            for m in matches:
                home_obj = m.get("home", {})
                away_obj = m.get("away", {})
                
                ev_sahibi = turkcelestir(metin_veya_sozlukten_al(home_obj, "name"), "takim")
                deplasman = turkcelestir(metin_veya_sozlukten_al(away_obj, "name"), "takim")
                
                # Maç saati ve diğer detaylar
                mac_zamani = m.get("time", "")
                
                # Veritabanına kaydetme veya güncelleme
                execute_d1(
                    """INSERT OR IGNORE INTO maclar (ev_sahibi, deplasman, saat, ev_skor, dep_skor) 
                       VALUES (?, ?, ?, 0, 0)""",
                    [ev_sahibi, deplasman, mac_zamani]
                )
                kaydedilen += 1

            print(f"✅ Günün bülteni yüklendi: {kaydedilen} maç işlendi.")
            if chat_id:
                telegram_post(f"✅ Günün bülteni başarıyla güncellendi! Toplam {kaydedilen} maç yüklendi.", chat_id)
        else:
            print(f"❌ Bülten API Hatası: {res.status_code} - {res.text}")
            if chat_id:
                telegram_post(f"❌ Güncelleme başarısız oldu. API Yanıt Kodu: {res.status_code}", chat_id)
            
    except Exception as e:
        print(f"❌ Bülten güncelleme kritik hata: {e}")
        if chat_id:
            telegram_post(f"❌ Kritik hata oluştu: {e}", chat_id)

    # Güncelleme bittikten sonra ana bülten mesajını ekrana bas
    if chat_id:
        msg, markup = get_paginated_matches_message(0)
        telegram_post(msg, chat_id, markup)
