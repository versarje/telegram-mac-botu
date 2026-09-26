import requests
from datetime import datetime, timedelta
import config
from db import db_baglan
from utils import telegram_post, turkcelestir, metin_veya_sozlukten_al, akilli_tahmin_uret

def api_yanitindan_maclari_ayikla(res_json):
    if isinstance(res_json, dict):
        for key in ["response", "events", "data", "matches", "results"]:
            val = res_json.get(key)
            if isinstance(val, list):
                return val
            elif isinstance(val, dict):
                sub_val = val.get("matches", val.get("events", []))
                if isinstance(sub_val, list):
                    return sub_val
    elif isinstance(res_json, list):
        return res_json
    return []

def gunun_maclarini_cek():
    su_an_tsi = datetime.utcnow() + timedelta(hours=3)
    formatli_tarih = su_an_tsi.strftime("%Y%m%d")
    headers = {
        "x-rapidapi-key": config.RAPIDAPI_KEY,
        "x-rapidapi-host": config.RAPIDAPI_HOST
    }
    url = f"{config.BASE_URL}/football-get-matches-by-date"
    try:
        res = requests.get(url, headers=headers, params={"date": formatli_tarih}, timeout=20)
        if res.status_code == 200:
            return api_yanitindan_maclari_ayikla(res.json())
    except Exception as e:
        print("❌ API İstek Hatası:", e)
    return []

def rastgele_bulten_tahmin_olustur(chat_id=None):
    su_an_tsi = datetime.utcnow() + timedelta(hours=3)
    tarih_gorunum = su_an_tsi.strftime("%Y-%m-%d")

    telegram_post("🔄 <b>Günün futbol bülteni ve oranları çekiliyor...</b>", chat_id)

    headers = {
        "x-rapidapi-key": config.RAPIDAPI_KEY,
        "x-rapidapi-host": config.RAPIDAPI_HOST
    }
    formatli_tarih = su_an_tsi.strftime("%Y%m%d")
    url = f"{config.BASE_URL}/football-get-matches-by-date"
    
    events = []
    kalan_istek = "Bilinmiyor"
    toplam_limit = "Bilinmiyor"

    try:
        res = requests.get(url, headers=headers, params={"date": formatli_tarih}, timeout=20)
        kalan_istek = res.headers.get("x-ratelimit-requests-remaining", "Bilinmiyor")
        toplam_limit = res.headers.get("x-ratelimit-requests-limit", "Bilinmiyor")

        if res.status_code == 200:
            events = api_yanitindan_maclari_ayikla(res.json())
    except Exception as e:
        print("❌ API İstek Hatası:", e)

    if not events:
        telegram_post("📅 Bugün için bültende maç bulunamadı veya API bağlantısı kurulamadı.", chat_id)
        return

    islenmis_maclar = []
    
    for i, m in enumerate(events):
        if not isinstance(m, dict):
            continue

        fid = str(m.get("id", m.get("match_id", m.get("eventId", i))))
        
        raw_lig = metin_veya_sozlukten_al(m.get("league"), "name") or \
                  metin_veya_sozlukten_al(m.get("tournament"), "name") or "Futbol"

        raw_ev = metin_veya_sozlukten_al(m.get("homeTeam"), "name") or \
                 metin_veya_sozlukten_al(m.get("home_team"), "name") or \
                 metin_veya_sozlukten_al(m.get("home"), "name") or "Ev Sahibi"

        raw_dep = metin_veya_sozlukten_al(m.get("awayTeam"), "name") or \
                  metin_veya_sozlukten_al(m.get("away_team"), "name") or \
                  metin_veya_sozlukten_al(m.get("away"), "name") or "Deplasman"

        lig = turkcelestir(raw_lig, tur="lig")
        ev = turkcelestir(raw_ev, tur="takim")
        dep = turkcelestir(raw_dep, tur="takim")

        time_val = m.get("time", m.get("start_time", ""))
        timestamp = m.get("startTimestamp", None)

        if timestamp and isinstance(timestamp, (int, float)):
            saat_tsi = (datetime.utcfromtimestamp(timestamp) + timedelta(hours=3)).strftime("%H:%M")
        elif time_val and ":" in str(time_val):
            saat_parca = str(time_val).split()
            saat_tsi = saat_parca[-1] if len(saat_parca) > 1 else str(time_val)
        else:
            saat_tsi = "99:99"

        odds_data = m.get("odds", m.get("mainOdds", {}))
        oran_metni = ""
        if isinstance(odds_data, dict) and odds_data:
            ms1 = odds_data.get("home", odds_data.get("1", "-"))
            msx = odds_data.get("draw", odds_data.get("X", "-"))
            ms2 = odds_data.get("away", odds_data.get("2", "-"))
            if ms1 != "-" or ms2 != "-":
                oran_metni = f"📊 Oranlar: MS1: <b>{ms1}</b> | MSX: <b>{msx}</b> | MS2: <b>{ms2}</b>\n"

        secilen_tahmin_metin, secilen_tahmin_tur = akilli_tahmin_uret(fid, ev, dep)

        islenmis_maclar.append({
            "fid": fid,
            "saat": saat_tsi,
            "lig": lig,
            "ev": ev,
            "dep": dep,
            "mac_adi": f"{ev} vs {dep}",
            "tahmin_metin": secilen_tahmin_metin,
            "tahmin_tur": secilen_tahmin_tur,
            "oran_metni": oran_metni
        })

    if not islenmis_maclar:
        telegram_post("⚠️ Bültendeki maç verileri uygun formatta okunamadı.", chat_id)
        return

    islenmis_maclar.sort(key=lambda x: x["saat"])

    mesaj_satirlari = [
        f"🎯 <b>GÜNÜN MAÇLARI VE TAHMİNLER ({tarih_gorunum})</b>",
        "-----------------------------------------"
    ]

    conn = db_baglan()
    islenen_mac_sayisi = 0

    try:
        with conn.cursor() as cursor:
            for item in islenmis_maclar[:15]:
                sql = """
                    INSERT INTO tahminler (match_id, mac, lig, saat, tahmin, tur, tarih)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE mac=%s, saat=%s, tarih=%s;
                """
                cursor.execute(sql, (
                    item["fid"], item["mac_adi"], item["lig"], item["saat"], 
                    item["tahmin_metin"], item["tahmin_tur"], tarih_gorunum,
                    item["mac_adi"], item["saat"], tarih_gorunum
                ))

                mesaj_satirlari.append(
                    f"⏰ <b>{item['saat']}</b> | 🏆 <i>{item['lig']}</i>\n"
                    f"⚔️ <b>{item['ev']} vs {item['dep']}</b>\n"
                    f"{item['oran_metni']}"
                    f"🎯 Tahmin: <b>{item['tahmin_metin']}</b>\n"
                )
                islenen_mac_sayisi += 1
    finally:
        conn.close()

    mesaj_satirlari.append("-----------------------------------------")
    mesaj_satirlari.append(
        f"💾 <b>{islenen_mac_sayisi} maç Aiven MySQL veritabanına kaydedildi.</b>\n"
        f"📊 <b>Kalan API Hakkınız:</b> {kalan_istek} / {toplam_limit}\n"
        f"<i>Maçlar bitince /sonuc yazarak kontrol edebilirsiniz.</i>"
    )

    telegram_post("\n".join(mesaj_satirlari), chat_id)

def ayrintili_mac_sonuclarini_getir(chat_id=None):
    su_an_tsi = datetime.utcnow() + timedelta(hours=3)
    tarih_gorunum = su_an_tsi.strftime("%Y-%m-%d")

    events = gunun_maclarini_cek()
    if not events:
        telegram_post("🏁 Maç sonuçları taranırken API verisi alınamadı.", chat_id)
        return

    biten_maclar = {}
    for m in events:
        if not isinstance(m, dict):
            continue

        fid = str(m.get("id", m.get("match_id", m.get("eventId", ""))))
        status_val = m.get("status", {})
        if isinstance(status_val, dict):
            status = str(status_val.get("type", status_val.get("description", ""))).lower()
        else:
            status = str(status_val).lower()

        if status in ["finished", "ft", "ended", "100"]:
            biten_maclar[fid] = m

    conn = db_baglan()
    tahminler = []
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM tahminler WHERE durum = '⏳ BEKLENİYOR'")
            bekleyenler_db = cursor.fetchall()

            for t_data in bekleyenler_db:
                fid = t_data["match_id"]
                if fid in biten_maclar:
                    m = biten_maclar[fid]
                    home_score = m.get("homeScore", {}).get("current", m.get("scores", {}).get("home", 0))
                    away_score = m.get("awayScore", {}).get("current", m.get("scores", {}).get("away", 0))

                    try:
                        home_score, away_score = int(home_score), int(away_score)
                    except:
                        home_score, away_score = 0, 0

                    toplam_gol = home_score + away_score
                    kg_var = (home_score > 0 and away_score > 0)
                    tur = t_data["tur"]
                    tuttu = False

                    if tur == "UST25" and toplam_gol > 2: tuttu = True
                    elif tur == "ALT25" and toplam_gol < 3: tuttu = True
                    elif tur == "KG_VAR" and kg_var: tuttu = True

                    yeni_skor = f"{home_score}-{away_score}"
                    yeni_durum = "✅ TUTTU" if tuttu else "❌ GELMEDİ"

                    cursor.execute("UPDATE tahminler SET skor = %s, durum = %s WHERE match_id = %s", (yeni_skor, yeni_durum, fid))

            cursor.execute("SELECT * FROM tahminler WHERE tarih = %s ORDER BY saat ASC", (tarih_gorunum,))
            tahminler = cursor.fetchall()
    finally:
        conn.close()

    if not tahminler:
        telegram_post("📊 Henüz bugün için kaydedilmiş maç yok.", chat_id)
        return

    tutanlar, yatanlar, bekleyenler = [], [], []

    for t in tahminler:
        metin = f"🔹 <b>{t['mac']}</b> ({t['skor']})\n🎯 Tahmin: <i>{t['tahmin']}</i>"
        if t["durum"] == "✅ TUTTU": tutanlar.append(metin)
        elif t["durum"] == "❌ GELMEDİ": yatanlar.append(metin)
        else: bekleyenler.append(f"⏳ <b>{t['mac']}</b> - <i>{t['tahmin']}</i>")

    rapor = [f"📊 <b>GÜNÜN TAHMİN SONUÇ RAPORU ({tarih_gorunum})</b>\n"]

    if tutanlar:
        rapor.append("✅ <b>TUTAN TAHMİNLER</b>\n" + "-----------------------------------------")
        rapor.extend(tutanlar)
        rapor.append("")

    if yatanlar:
        rapor.append("❌ <b>TUTMAYAN TAHMİNLER</b>\n" + "-----------------------------------------")
        rapor.extend(yatanlar)
        rapor.append("")

    if bekleyenler:
        rapor.append("⏳ <b>HENÜZ BİTMEYEN MAÇLAR</b>\n" + "-----------------------------------------")
        rapor.extend(bekleyenler[:5])
        rapor.append("")

    toplam_biten = len(tutanlar) + len(yatanlar)
    basari_yuzde = round((len(tutanlar) / toplam_biten) * 100, 1) if toplam_biten > 0 else 0
    rapor.append(f"📈 <b>Özet:</b> {len(tutanlar)} Tutan / {len(yatanlar)} Yatan | Başarı: <b>%{basari_yuzde}</b>")

    telegram_post("\n".join(rapor), chat_id)

# bot.py dosyasının EN ALTINA ekleyin:

def canli_maclari_getir(chat_id=None):
    """O an oynanmakta olan canlı maçları ve anlık skorlarını Telegram'a gönderir."""
    telegram_post("🔴 <b>Oynanmakta olan canlı maçlar taranıyor...</b>", chat_id)

    headers = {
        "x-rapidapi-key": config.RAPIDAPI_KEY,
        "x-rapidapi-host": config.RAPIDAPI_HOST
    }
    url = f"{config.BASE_URL}/football-get-live-matches"

    try:
        res = requests.get(url, headers=headers, timeout=20)
        kalan_istek = res.headers.get("x-ratelimit-requests-remaining", "Bilinmiyor")
        
        if res.status_code == 200:
            events = api_yanitindan_maclari_ayikla(res.json())
            
            if not events:
                telegram_post("⚽ Şu anda oynanan canlı maç bulunamadı.", chat_id)
                return

            mesaj_satirlari = [
                "🔴 <b>CANLI MAÇLAR VE ANLIK DURUM</b>",
                "-----------------------------------------"
            ]

            for m in events[:15]:  # En fazla 15 canlı maç göster
                if not isinstance(m, dict):
                    continue

                raw_ev = metin_veya_sozlukten_al(m.get("homeTeam"), "name") or "Ev Sahibi"
                raw_dep = metin_veya_sozlukten_al(m.get("awayTeam"), "name") or "Deplasman"
                ev = turkcelestir(raw_ev, tur="takim")
                dep = turkcelestir(raw_dep, tur="takim")

                # Canlı Skor Verisi
                home_score = m.get("homeScore", {}).get("current", 0) if isinstance(m.get("homeScore"), dict) else 0
                away_score = m.get("awayScore", {}).get("current", 0) if isinstance(m.get("awayScore"), dict) else 0
                
                # Dakika / Durum Bilgisi
                status_obj = m.get("status", {})
                if isinstance(status_obj, dict):
                    dakika = status_obj.get("description", status_obj.get("reason", "Canlı"))
                else:
                    dakika = "Canlı"

                mesaj_satirlari.append(
                    f"⏱️ <b>[{dakika}]</b> ⚔️ <b>{ev} {home_score} - {away_score} {dep}</b>"
                )

            mesaj_satirlari.append("-----------------------------------------")
            mesaj_satirlari.append(f"📊 <b>Kalan API Hakkınız:</b> {kalan_istek}")
            
            telegram_post("\n".join(mesaj_satirlari), chat_id)
        else:
            telegram_post("❌ Canlı maçlar çekilirken API hatası oluştu.", chat_id)
    except Exception as e:
        print("❌ Canlı Maç Hatası:", e)
        telegram_post(f"❌ Bir hata oluştu: {e}", chat_id)

