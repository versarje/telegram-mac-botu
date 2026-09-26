import os
import threading
from flask import Flask, request, jsonify

from bot import bulteni_apiden_veritabanina_yukle, veritabanindan_bulten_getir
from db import tablo_kur

app = Flask(__name__)

# Sunucu başlarken MySQL tablosunun varlığını teyit et
tablo_kur()

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "status": "online",
        "message": "Futbol Bülten Bot Servisi Çalışıyor!"
    }), 200

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    data = request.get_json(silent=True) or {}
    message = data.get("message") or data.get("edited_message") or {}
    text = message.get("text", "").strip()
    chat_id = message.get("chat", {}).get("id")

    if text and chat_id:
        komut = text.split()[0].lower()

        # 1. API'den maç çekme komutu
        if komut in ["/guncelle", "/bulten_guncelle", "/fetch"]:
            threading.Thread(
                target=bulteni_apiden_veritabanina_yukle, 
                args=(chat_id,)
            ).start()

        # 2. Veritabanından çekme komutu
        elif komut in ["/bbb", "/ototahmin", "/bulten"]:
            threading.Thread(
                target=veritabanindan_bulten_getir, 
                args=(chat_id,)
            ).start()

    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
