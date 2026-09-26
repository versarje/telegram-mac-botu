import os
from flask import Flask, request
import bot
from db import init_d1_db

app = Flask(__name__)

@app.route('/', methods=['GET'])
def index():
    return "Bot Aktif ve Çalışıyor!", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(silent=True)
    if not data or "message" not in data:
        return "OK", 200

    message = data["message"]
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "").strip()

    if text in ["/start", "/help"]:
        bot.telegram_post(
            "👋 <b>Futbol Tahmin Botuna Hoş Geldiniz!</b>\n\n"
            "Komutlar:\n"
            "⚽ <b>/guncelle</b> - Günün maçlarını çeker ve tahminleri veritabanına kaydeder.\n"
            "🏆 <b>/skorlar</b> - Dün ve bugünün biten maç skorlarını ve tahmin başarı oranını getirir.", 
            chat_id
        )
    elif text == "/guncelle":
        bot.bulteni_apiden_veritabanina_yukle(chat_id)
    elif text in ["/skorlar", "/sonuclar"]:
        bot.biten_maclari_getir(chat_id)

    return "OK", 200

if __name__ == "__main__":
    init_d1_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
