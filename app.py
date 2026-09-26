import threading
from flask import Flask, request, jsonify
import config
from bot import (
    bulteni_apiden_veritabanina_yukle,
    veritabanindan_bulten_getir,
    telegram_post
)

app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "Bot Servisi Aktif!", 200

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json(silent=True) or {}
    
    if "message" in data:
        message = data["message"]
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip()

        if text.startswith("/"):
            komut = text.split()[0].lower()

            if komut in ["/start", "/yardim"]:
                mesaj = (
                    "🤖 <b>Futbol Tahmin Botu</b>\n\n"
                    "📌 <b>Komutlar:</b>\n"
                    "▫️ /guncelle - Güncel bülteni API'den çeker ve veritabanına kaydeder.\n"
                    "▫️ /bbb - Günün kalan maçlarını ve tahminleri listeler.\n"
                    "▫️ /bbb_all - Saat filtresiz veritabanındaki tüm maçları listeler (Test)."
                )
                telegram_post(mesaj, chat_id)

            elif komut in ["/guncelle", "/update"]:
                threading.Thread(
                    target=bulteni_apiden_veritabanina_yukle, 
                    args=(chat_id,)
                ).start()

            elif komut in ["/bbb", "/ototahmin", "/bulten"]:
                threading.Thread(
                    target=veritabanindan_bulten_getir, 
                    args=(chat_id, True)
                ).start()

            elif komut in ["/bbb_all", "/hepsi"]:
                threading.Thread(
                    target=veritabanindan_bulten_getir, 
                    args=(chat_id, False)
                ).start()

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
