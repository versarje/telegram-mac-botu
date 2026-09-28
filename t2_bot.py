import os
import time
import requests
import threading
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

# ================= ==========================================
# AYARLAR (Bağımsız T2 Canlı Analiz Botu)
# ================= ==========================================
TELEGRAM_BOT_TOKEN = "8894398415:AAEY_ffz8iPL8qZ8vJq3bgat7cibeQFhvI8"
TELEGRAM_CHAT_ID = "-1003991937105"

def send_telegram_message(chat_id, message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        response = requests.post(url, json=payload, timeout=15)
        return response.json()
    except Exception as e:
        print(f"Telegram mesaj gönderme hatası: {e}", flush=True)
        return None

def send_telegram_photo(chat_id, photo_path, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, 'rb') as f:
            files = {'photo': f}
            data = {'chat_id': chat_id, 'caption': caption, 'parse_mode': 'HTML'}
            response = requests.post(url, data=data, files=files, timeout=25)
            return response.json()
    except Exception as e:
        print(f"Fotoğraf gönderme hatası: {e}", flush=True)
        return None

def canli_mac_analiz_uret(ev_sahibi, deplasman, skor_ev, skor_dep, dakika_str):
    toplam_gol = skor_ev + skor_dep
    try:
        dakika = int(''.join(filter(str.isdigit, dakika_str)))
    except:
        dakika = 45

    if toplam_gol >= 3:
        tahmin = "4.5 Üst & Karşılıklı Gol Var"
        yorum = f"Dakika {dakika}: Müthiş bir gol düellosu yaşanıyor, goller devam eder."
    elif toplam_gol == 0 and dakika > 60:
        tahmin = "Tek Gol & Sonradan Açılır"
        yorum = f"Dakika {dakika}: Baskı arttı, ilk golü atan maçı koparır."
    elif skor_ev != skor_dep:
        tahmin = "Favori Baskıda / 1.5 Üst"
        yorum = f"Dakika {dakika}: Geride olan takım risk alıyor, açık alanlar doğuyor."
    else:
        tahmin = "Sıradaki Golü Atan Kazanır"
        yorum = f"Dakika {dakika}: Skor dengede, takımlar kontrollü oynuyor."
        
    return tahmin, yorum

def canli_bulten_gorseli_uret(canli_maclar):
    genislik = 950
    baslik_h = 100
    footer_h = 50
    satir_h = 160
    
    uretilen_dosyalar = []
    if not canli_maclar:
        img = Image.new("RGB", (genislik, 400), color="#0F172A")
        draw = ImageDraw.Draw(img)
        try:
            font_baslik = ImageFont.truetype("arialbd.ttf", 22)
            font_mac = ImageFont.truetype("arialbd.ttf", 15)
        except:
            font_baslik = ImageFont.load_default()
            font_mac = ImageFont.load_default()
            
        draw.rectangle([(0, 0), (genislik, baslik_h)], fill="#1E293B")
        draw.text((30, 22), "🔴 T2 CANLI MAÇLAR & ANLIK ANALİZLER", fill="#EF4444", font=font_baslik)
        draw.text((50, 180), "Şu anda oynanan canlı maç bulunmuyor.", fill="#FFFFFF", font=font_mac)
        dosya_adi = "t2_canli_p1.png"
        img.save(dosya_adi)
        return [dosya_adi]

    MASH_PER_PAGE = 4
    sayfa_listeleri = [canli_maclar[i:i + MASH_PER_PAGE] for i in range(0, len(canli_maclar), MASH_PER_PAGE)]
    toplam_sayfa = len(sayfa_listeleri)
    
    for idx, sayfa_maclari in enumerate(sayfa_listeleri):
        sayfa_no = idx + 1
        sayfa_h = baslik_h + footer_h + (len(sayfa_maclari) * satir_h) + 30
        
        img = Image.new("RGB", (genislik, max(sayfa_h, 500)), color="#0F172A")
        draw = ImageDraw.Draw(img)
        
        try:
            font_baslik = ImageFont.truetype("arialbd.ttf", 22)
            font_mac = ImageFont.truetype("arialbd.ttf", 15)
            font_detay = ImageFont.truetype("arial.ttf", 13)
            font_kucuk = ImageFont.truetype("arial.ttf", 12)
        except:
            font_baslik = ImageFont.load_default()
            font_mac = ImageFont.load_default()
            font_detay = ImageFont.load_default()
            font_kucuk = ImageFont.load_default()

        draw.rectangle([(0, 0), (genislik, baslik_h)], fill="#1E293B")
        draw.text((30, 22), f"🔴 T2 CANLI ANALİZLER - Sayfa {sayfa_no}/{toplam_sayfa}", fill="#EF4444", font=font_baslik)
        draw.text((30, 56), f"Bağımsız T2 Modülü | Anlık Skor ve Yapay Zeka Tahminleri", fill="#94A3B8", font=font_detay)
        
        y = baslik_h + 20
        for mac in sayfa_maclari:
            draw.rectangle([(20, y), (genislik - 20, y + 150)], fill="#1E293B")
            
            # Skor ve Dakika Kutusu (Sol)
            draw.rectangle([(20, y), (150, y + 150)], fill="#7F1D1D")
            draw.text((30, y + 45), f"Dakika: {mac['dakika']}", fill="#FCA5A5", font=font_kucuk)
            draw.text((30, y + 75), f"{mac['skor_ev']} - {mac['skor_dep']}", fill="#FFFFFF", font=font_baslik)
            
            # Takımlar
            mac_adi = f"{mac['ev_sahibi']}  vs  {mac['deplasman']}"
            draw.text((170, y + 15), mac_adi, fill="#FFFFFF", font=font_mac)
            
            draw.line([(170, y + 45), (genislik - 40, y + 45)], fill="#475569", width=1)
            
            draw.text((170, y + 60), f"⚡ Canlı Tahmin: {mac['tahmin']}", fill="#4ADE80", font=font_detay)
            draw.text((170, y + 95), f"💡 Canlı Yorum: {mac['yorum']}", fill="#CBD5E1", font=font_kucuk)
            
            y += 160

        draw.rectangle([(0, img.height - footer_h), (genislik, img.height)], fill="#0F172A")
        draw.text((30, img.height - 33), f"🤖 T2 Bağımsız Canlı Bot  |  Sayfa {sayfa_no} / {toplam_sayfa}", fill="#64748B", font=font_detay)

        dosya_adi = f"t2_canli_p{sayfa_no}.png"
        img.save(dosya_adi)
        uretilen_dosyalar.append(dosya_adi)
        
    return uretilen_dosyalar

def t2_canli_analiz_gonder(chat_id):
    send_telegram_message(chat_id, "🔴 <b>T2 Bot: Canlı maçlar taranıyor ve anlık analiz yapılıyor...</b>")
    try:
        today_str = time.strftime("%Y%m%d")
        api_url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={today_str}"
        res = requests.get(api_url, timeout=12)
        
        canli_maclar = []
        if res.status_code == 200:
            events = res.json().get("events", [])
            for event in events:
                status_type = event.get("status", {}).get("type", {}).get("name", "")
                if status_type == "STATUS_IN_PROGRESS":
                    status_detail = event.get("status", {}).get("type", {}).get("shortDetail", "Devam Ediyor")
                    competitors = event.get("competitions", [{}])[0].get("competitors", [])
                    if len(competitors) >= 2:
                        ev = competitors[0].get("team", {}).get("displayName", "")
                        dep = competitors[1].get("team", {}).get("displayName", "")
                        score_ev = int(competitors[0].get("score", 0))
                        score_dep = int(competitors[1].get("score", 0))
                        
                        tahmin, yorum = canli_mac_analiz_uret(ev, dep, score_ev, score_dep, status_detail)
                        
                        canli_maclar.append({
                            "ev_sahibi": ev,
                            "deplasman": dep,
                            "skor_ev": score_ev,
                            "skor_dep": score_dep,
                            "dakika": status_detail,
                            "tahmin": tahmin,
                            "yorum": yorum
                        })
        
        dosyalar = canli_bulten_gorseli_uret(canli_maclar)
        toplam = len(dosyalar)
        for idx, dosya in enumerate(dosyalar):
            sayfa_no = idx + 1
            caption = f"🔴 <b>T2 Canlı Maç Analizleri (Sayfa {sayfa_no}/{toplam})</b>"
            send_telegram_photo(chat_id, dosya, caption)
            time.sleep(0.5)
            
    except Exception as e:
        print(f"T2 Canlı analiz hatası: {e}", flush=True)
        send_telegram_message(chat_id, "⚠️ T2 Canlı maçlar taranırken bir hata oluştu.")

# ================= ==========================================
# FLASK WEBHOOK VE SUNUCU
# ================= ==========================================
@app.route('/')
def home():
    return "T2 Bağımsız Canlı Analiz Botu Aktif!"

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    if update and "message" in update:
        message_data = update["message"]
        text = message_data.get("text", "").strip().lower()
        chat_id = message_data.get("chat", {}).get("id")
        
        if text == "!t2" and chat_id:
            print(f"T2 Bot: !t2 komutu algılandı (Chat ID: {chat_id})", flush=True)
            t2_canli_analiz_gonder(chat_id)
            
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    print("T2 Bağımsız Canlı Bot başlatılıyor...", flush=True)
    # Farklı bir port veya ana bottan bağımsız çalışma ortamı
    port = int(os.environ.get("PORT", 10001))
    app.run(host='0.0.0.0', port=port, threaded=True)
