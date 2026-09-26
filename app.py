from flask import Flask, request, jsonify
import bot
import config

app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "Bot Aktif ve Çalışıyor!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(silent=True)
    if not update:
        return jsonify({"status": "error"}), 400

    message = update.get("message") or update.get("edited_message")
    if not message:
        return jsonify({"status": "ok"}), 200

    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "").strip()

    if not text or not chat_id:
        return jsonify({"status": "ok"}), 200

    komut = text.split()[0].lower()

    if komut in ["/start", "/yardim"]:
        mesaj = (
            "🤖 <b>Futbol Tahmin Botu</b>\n\n"
            "📌 <b>Komutlar:</b>\n"
            "▫️ /guncelle - Güncel bülteni API'den çeker.\n"
            "▫️ /bbb - Günün kalan maçlarını listeler.\n"
            "▫️ /bbb_all - Tüm maçları listeler."
        )
        bot.telegram_post(mesaj, chat_id)

    elif komut in ["/guncelle", "/update"]:
        bot.bulteni_apiden_veritabanina_yukle(chat_id)

    elif komut in ["/bbb", "/ototahmin", "/bulten"]:
        bot.veritabanindan_bulten_getir(chat_id, filtreli=True)

    elif komut in ["/bbb_all", "/hepsi"]:
        bot.veritabanindan_bulten_getir(chat_id, filtreli=False)

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
