import os
import threading
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
    if not data:
        return "OK", 200

    # Sayfalama Butonları (Önceki / Sonraki)
    if "callback_query" in data:
        cq = data["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        message_id = cq["message"]["message_id"]
        callback_data = cq.get("data", "")

        if callback_data.startswith("page_"):
            try:
                page_num = int(callback_data.split("_")[1])
                text, markup = bot.get_paginated_matches_message(page_num)
                bot.telegram_edit_message(chat_id, message_id, text, markup)
            except Exception as e:
                print(f"Callback error: {e}")

        return "OK", 200

    # Normal Komutlar
    if "message" in data:
        message = data["message"]
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip()

        if text in ["/start", "/help"]:
            bot.telegram_post(
                "👋 <b>Futbol Tahmin Botuna Hoş Geldiniz!</b>\n\n"
                "Komutlar:\n"
                "⚽ <b>/guncelle</b> - Bugünün bültenini ve tahminlerini çeker.\n"
                "📅 <b>/yarin</b> - Yarının bültenini çeker.\n"
                "🏆 <b>/skorlar</b> - Canlı skor API'sinden verileri günceller ve listeler.", 
                chat_id
            )
        elif text == "/guncelle":
            threading.Thread(target=bot.bulteni_apiden_veritabanina_yukle, args=(chat_id,)).start()
        elif text == "/yarin":
            threading.Thread(target=bot.yarin_bultenini_yukle, args=(chat_id,)).start()
        elif text in ["/skorlar", "/sonuclar", "/maclar"]:
            threading.Thread(target=bot.canli_skorlari_guncelle_ve_getir, args=(chat_id,)).start()

    return "OK", 200

if __name__ == "__main__":
    init_d1_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
