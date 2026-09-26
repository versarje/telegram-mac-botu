import os
import threading
from flask import Flask, request, jsonify
from db import tablo_kur
from bot import rastgele_bulten_tahmin_olustur, ayrintili_mac_sonuclarini_getir

app = Flask(__name__)

# Tablo Kontrolü
tablo_kur()

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json()
    if update and "message" in update:
        message = update["message"]
        text = message.get("text", "").strip()
        chat_id = message["chat"]["id"]

        parcalar = text.split()
        komut = parcalar[0].lower() if parcalar else ""

        if komut in ["/bbb", "/ototahmin"]:
            threading.Thread(target=rastgele_bulten_tahmin_olustur, args=(chat_id,)).start()

        elif komut in ["/sonuc", "/sonuclar", "/bitenler", "/rapor"]:
            threading.Thread(target=ayrintili_mac_sonuclarini_getir, args=(chat_id,)).start()

    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

from flask import Flask, request
import threading

# 1. bot.py'den yeni fonksiyonu içe aktarın:
from bot import rastgele_bulten_tahmin_olustur, ayrintili_mac_sonuclarini_getir, canli_maclari_getir
from db import tablo_kur

app = Flask(__name__)

# Sunucu başlarken veritabanı tablosunu kontrol et
tablo_kur()

@app.route("/", methods=["GET"])
def home():
    return "Bot Servisi Aktif!", 200

@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json(silent=True) or {}
    message = data.get("message") or data.get("edited_message") or {}
    text = message.get("text", "").strip()
    chat_id = message.get("chat", {}).get("id")

    if text and chat_id:
        komut = text.split()[0].lower()

        if komut in ["/bbb", "/ototahmin"]:
            threading.Thread(target=rastgele_bulten_tahmin_olustur, args=(chat_id,)).start()

        # 2. Canlı maç komutunu buraya ekleyin:
        elif komut in ["/canli", "/live", "/canlimaclar"]:
            threading.Thread(target=canli_maclari_getir, args=(chat_id,)).start()

        elif komut in ["/sonuc", "/sonuclar", "/bitenler", "/rapor"]:
            threading.Thread(target=ayrintili_mac_sonuclarini_getir, args=(chat_id,)).start()

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

