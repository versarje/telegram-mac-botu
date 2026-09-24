import os
import math
import time
import sqlite3
import requests
import threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# ==========================================
# ⚙️ KONFİGÜRASYONLAR
# ==========================================
API_KEY = "b699d9effa443321a65fd145ec78ede1"
BASE_URL = "https://v3.football.api-sports.io"
TELEGRAM_BOT_TOKEN = "8894398415:AAEY_ffz8iPL8qZ8vJq3bgat7cibeQFhvI8"
TELEGRAM_CHAT_ID = "-1004461429503"

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
DB_YOLU = os.path.join(BASE_DIR, "maclar.db")

HEADERS = {
    "x-apisports-key": API_KEY,
    "Accept": "application/json"
}

LIG_ID_BONUS = [39, 140, 135, 78, 61, 88, 203, 144, 94, 2, 3, 848, 5]

# ==========================================
# 1. VERİTABANI VE YARDIMCI FONKSİYONLAR
# ==========================================
def veritabanini_kur():
    conn = sqlite3.connect(DB_YOLU)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS maclar (
            fixture_id INTEGER PRIMARY KEY,
            league_id INTEGER,
            tarih TEXT,
            saat TEXT,
            lig TEXT,
            ev_sahibi TEXT,
            deplasman TEXT,
            ev_gol INTEGER DEFAULT NULL,
            dep_gol INTEGER DEFAULT NULL,
            durum TEXT,
            ms1 REAL, msx REAL, ms2 REAL,
            ust25 REAL, alt25 REAL,
            kg_var REAL, kg_yok REAL,
            ai_ust25_olasilik REAL DEFAULT 0,
            ai_kgvar_olasilik REAL DEFAULT 0,
            ai_tahmin TEXT DEFAULT NULL,
            tahmin_basari INTEGER DEFAULT NULL,
            bildirildi INTEGER DEFAULT 0,
            guncellenme_tarihi DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def telegram_post(metin, chat_id=None):
    target_chat = chat_id if chat_id else TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": metin,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Telegram gonderme hatasi:", e)

# ==========================================
# 2. VERİ ÇEKME VE ANALİZ MOTORU
# ==========================================
def maclari_cek_ve_guncelle(tarih_str):
    url = f"{BASE_URL}/fixtures"
    params = {"date": tarih_str, "timezone": "Europe/Istanbul"}
    try:
        res = requests.get(url, params=params, headers=HEADERS, timeout=30)
        data = res.json().get("response", [])
        if not data: return False

        conn = sqlite3.connect(DB_YOLU)
        cursor = conn.cursor()
        for m in data:
            f, t, g, l = m["fixture"], m["teams"], m["goals"], m["league"]
            cursor.execute("""
                INSERT INTO maclar (fixture_id, league_id, tarih, saat, lig, ev_sahibi, deplasman, ev_gol, dep_gol, durum)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fixture_id) DO UPDATE SET
                    league_id = excluded.league_id,
                    ev_gol = excluded.ev_gol,
                    dep_gol = excluded.dep_gol,
                    durum = excluded.durum
            """, (f["id"], l["id"], tarih_str, f["date"][11:16], l["name"], t["home"]["name"], t["away"]["name"], g["home"], g["away"], f["status"]["short"]))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("Mac cekme hatasi:", e)
        return False

def oranlari_cek_ve_guncelle(tarih_str):
    url = f"{BASE_URL}/odds"
    conn = sqlite3.connect(DB_YOLU)
    cursor = conn.cursor()
    for page in range(1, 6):
        try:
            res = requests.get(url, params={"date": tarih_str, "page": page}, headers=HEADERS, timeout=30)
            data = res.json()
            for item in data.get("response", []):
                fid = item["fixture"]["id"]
                bookmakers = item.get("bookmakers", [])
                if not bookmakers: continue
                ms1 = msx = ms2 = ust25 = alt25 = kg_var = kg_yok = None
                for bet in bookmakers[0].get("bets", []):
                    b_id = bet.get("id")
                    if b_id == 1:
                        for v in bet.get("values", []):
                            if v["value"] == "Home": ms1 = float(v["odd"])
                            elif v["value"] == "Draw": msx = float(v["odd"])
                            elif v["value"] == "Away": ms2 = float(v["odd"])
                    elif b_id == 5:
                        for v in bet.get("values", []):
                            if v["value"] == "Over 2.5": ust25 = float(v["odd"])
                            elif v["value"] == "Under 2.5": alt25 = float(v["odd"])
                    elif b_id == 8:
                        for v in bet.get("values", []):
                            if v["value"] == "Yes": kg_var = float(v["odd"])
                            elif v["value"] == "No": kg_yok = float(v["odd"])

                cursor.execute("""
                    UPDATE maclar 
                    SET ms1 = ?, msx = ?, ms2 = ?, ust25 = ?, alt25 = ?, kg_var = ?, kg_yok = ?
                    WHERE fixture_id = ? AND ust25 IS NULL
                """, (ms1, msx, ms2, ust25, alt25, kg_var, kg_yok, fid))
        except: break
    conn.commit()
    conn.close()

def poisson_gol_olasiligi(lmbda, k):
    return (math.pow(lmbda, k) * math.exp(-lmbda)) / math.factorial(k)

def yapay_zeka_analiz_et(tarih_str):
    conn = sqlite3.connect(DB_YOLU)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT fixture_id, league_id, ust25, alt25, kg_var, kg_yok 
        FROM maclar 
        WHERE tarih = ? AND durum NOT IN ('FT', 'AET', 'PEN', 'CANC') AND ai_tahmin IS NULL
    """, (tarih_str,))
    maclar = cursor.fetchall()

    for m in maclar:
        fid, lid, ust25, alt25, kg_var, kg_yok = m
        eff_ust = ust25 if ust25 else 1.80
        eff_kg = kg_var if kg_var else 1.80

        prob_ust_implied = (1 / eff_ust) * 100
        prob_kg_implied = (1 / eff_kg) * 100
        beklenen_toplam_gol = 2.5 * (1.85 / eff_ust)

        p_ev_0 = poisson_gol_olasiligi(beklenen_toplam_gol / 2, 0)
        p_dep_0 = poisson_gol_olasiligi(beklenen_toplam_gol / 2, 0)
        p_kg_yok = p_ev_0 + p_dep_0 - (p_ev_0 * p_dep_0)
        p_kg_var_poisson = (1 - p_kg_yok) * 100
        p_ust_poisson = min((beklenen_toplam_gol / 2.5) * 55, 90)

        ai_ust_score = (p_ust_poisson * 0.6) + (prob_ust_implied * 0.4)
        ai_kg_score = (p_kg_var_poisson * 0.6) + (prob_kg_implied * 0.4)

        if lid in LIG_ID_BONUS:
            ai_ust_score += 5.0
            ai_kg_score += 4.0

        ai_ust_score = round(min(ai_ust_score, 95.0), 1)
        ai_kg_score = round(min(ai_kg_score, 95.0), 1)

        tahmin = "⚽ 2.5 ÜST POTANSİYELİ"
        if ai_ust_score >= 52.0 and ai_kg_score >= 50.0: tahmin = "🔥 2.5 ÜST & KG VAR"
        elif ai_ust_score >= 48.0: tahmin = "⚽ 2.5 ÜST"
        elif ai_kg_score >= 46.0: tahmin = "🤝 KG VAR"

        cursor.execute("UPDATE maclar SET ai_ust25_olasilik = ?, ai_kgvar_olasilik = ?, ai_tahmin = ? WHERE fixture_id = ?", (ai_ust_score, ai_kg_score, tahmin, fid))
    conn.commit()
    conn.close()

def telegram_ai_bulten_gonder(tarih_str, saat_str):
    conn = sqlite3.connect(DB_YOLU)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT fixture_id, saat, lig, ev_sahibi, deplasman, ust25, kg_var, ai_ust25_olasilik, ai_kgvar_olasilik, ai_tahmin, durum
        FROM maclar 
        WHERE tarih = ? AND durum IN ('NS', '1H', 'HT', '2H', 'LIVE') AND saat >= ? AND ai_tahmin IS NOT NULL AND bildirildi = 0
        ORDER BY saat ASC
    """, (tarih_str, saat_str))
    maclar = cursor.fetchall()
    if not maclar:
        conn.close()
        return

    baslik = f"🤖 <b>AI FOOTBALL BÜLTENİ</b> ({tarih_str})\n⏰ <i>Saat {saat_str} (TSİ) Sonrası / Canlı Maçlar ({len(maclar)} Maç)</i>\n=============================\n\n"
    parca_mesaj = baslik

    for m in maclar:
        fid, saat, lig, ev, dep, ust25, kg_var, ai_ust, ai_kg, tahmin, durum = m
        durum_etiketi = "🔴 CANLI" if durum in ['1H', '2H', 'HT', 'LIVE'] else f"⏰ {saat}"

        mac_metni = (
            f"{durum_etiketi} | 🏆 <code>{lig}</code>\n"
            f"⚔️ <b>{ev} vs {dep}</b>\n"
            f"🎯 <b>AI TAHMİNİ:</b> <u>{tahmin}</u>\n"
            f"📈 <b>2.5 Üst Güveni:</b> %{ai_ust} | Oran: <code>{ust25 if ust25 else 'N/A'}</code>\n"
            f"⚽ <b>KG Var Güveni:</b> %{ai_kg} | Oran: <code>{kg_var if kg_var else 'N/A'}</code>\n"
            f"-----------------------------------------\n"
        )
        if len(parca_mesaj) + len(mac_metni) > 3800:
            telegram_post(parca_mesaj)
            parca_mesaj = ""
        parca_mesaj += mac_metni
        cursor.execute("UPDATE maclar SET bildirildi = 1 WHERE fixture_id = ?", (fid,))

    if parca_mesaj: telegram_post(parca_mesaj)
    conn.commit()
    conn.close()

# ==========================================
# 3. OTOMATİK BİTEN MAÇLARI TEK TEK BİLDİRME
# ==========================================
def otomatik_biten_maclari_kontrol_et():
    """Arka planda çalışıp biten maçları TEK TEK gruba bildirir."""
    su_an = datetime.utcnow() + timedelta(hours=3)
    tarih_str = su_an.strftime("%Y-%m-%d")
    
    veritabanini_kur()
    maclari_cek_ve_guncelle(tarih_str) # Skorları güncelle
    
    conn = sqlite3.connect(DB_YOLU)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT fixture_id, lig, ev_sahibi, deplasman, ev_gol, dep_gol, ai_tahmin
        FROM maclar
        WHERE durum IN ('FT', 'AET', 'PEN') AND ai_tahmin IS NOT NULL AND tahmin_basari IS NULL
    """)
    biten_maclar = cursor.fetchall()
    
    for m in biten_maclar:
        fid, lig, ev, dep, ev_gol, dep_gol, tahmin = m
        toplam_gol = (ev_gol if ev_gol else 0) + (dep_gol if dep_gol else 0)
        kg_durum = (ev_gol > 0 and dep_gol > 0)
        basarili = False

        if "2.5 ÜST & KG VAR" in tahmin:
            if toplam_gol >= 3 and kg_durum: basarili = True
        elif "2.5 ÜST" in tahmin:
            if toplam_gol >= 3: basarili = True
        elif "KG VAR" in tahmin:
            if kg_durum: basarili = True

        durum_emoji = "✅ KAZANDI" if basarili else "❌ KAYBETTİ"
        
        # TEK TEK ÖZEL BİLDİRİM MESAJI
        mesaj = (
            f"🏁 <b>MAÇ SONUÇLANDI!</b>\n"
            f"🏆 <code>{lig}</code>\n"
            f"⚔️ <b>{ev} {ev_gol} - {dep_gol} {dep}</b>\n"
            f"🎯 <b>AI Tahmini:</b> {tahmin}\n"
            f"📌 <b>Sonuç:</b> {durum_emoji}"
        )
        telegram_post(mesaj)
        cursor.execute("UPDATE maclar SET tahmin_basari = ? WHERE fixture_id = ?", (1 if basarili else 0, fid))

    conn.commit()
    conn.close()

# ==========================================
# 4. ARKA PLAN ZAMANLAYICISI (CRON JOB)
# ==========================================
scheduler = BackgroundScheduler()
# Her 10 dakikada bir otomatik maç skorlarını ve biten maçları tarar
scheduler.add_job(func=otomatik_biten_maclari_kontrol_et, trigger="interval", minutes=10)
scheduler.start()

# ==========================================
# 5. FLASK WEBHOOK
# ==========================================
def bot_gorevini_calistir(chat_id):
    su_an = datetime.utcnow() + timedelta(hours=3)
    tarih_str = su_an.strftime("%Y-%m-%d")
    saat_str = su_an.strftime("%H:%M")
    
    telegram_post("⏳ <b>Analiz ve güncelleme başlatıldı...</b> Lütfen bekleyin.", chat_id)
    try:
        veritabanini_kur()
        if maclari_cek_ve_guncelle(tarih_str):
            oranlari_cek_ve_guncelle(tarih_str)
            yapay_zeka_analiz_et(tarih_str)
            telegram_ai_bulten_gonder(tarih_str, saat_str)
            otomatik_biten_maclari_kontrol_et()
            telegram_post("✅ <b>İşlem tamamlandı! Bülten gruba iletildi.</b>", chat_id)
        else:
            telegram_post("⚠️ Bugüne ait analiz edilecek maç verisi bulunamadı.", chat_id)
    except Exception as e:
        telegram_post(f"❌ Hata oluştu: {str(e)}", chat_id)

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json()
    if update and "message" in update:
        message = update["message"]
        text = message.get("text", "").strip()
        chat_id = message["chat"]["id"]
        
        if text.lower() == "!analiz":
            threading.Thread(target=bot_gorevini_calistir, args=(chat_id,)).start()
            
    return jsonify({"status": "ok"}), 200

@app.route('/', methods=['GET'])
def home():
    return "AI Football Bot Webhook & Oto Takip Sunucusu Aktif!", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
