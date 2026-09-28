import asyncio
import os
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import datetime
import requests

# ==========================================
# 1. TELEGRAM BİLGİLERİ (ENV VARIABLES)
# ==========================================

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8894398415:AAEY_ffz8iPL8qZ8vJq3bgat7cibeQFhvI8")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-1004461429503")
 

TRACKED_MATCHES = {}

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Telegram Token veya Chat ID eksik!")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            print("✅ Bildirim Telegram'a iletildi.")
        else:
            print(f"❌ Telegram Hatası: {res.text}")
    except Exception as e:
        print(f"Hata: {e}")

async def fetch_live_matches(page):
    matches = {}
    try:
        search_url = "https://www.google.com/search?q=günün+futbol+maçları&hl=tr"
        await page.goto(search_url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1500)

        content = await page.content()
        soup = BeautifulSoup(content, "html.parser")

        card_elements = soup.select("div.imso-toa, div.K6L4xe, div[data-df-id]")

        for card in card_elements[:6]:
            try:
                teams = card.select("span.imso_bh, div.ellipsisize_text, span.hs2a1e")
                scores = card.select("span.imso_mh_l_s, span.imso_mh_r_s, div.imso_mh_s")
                status_elem = card.select_one("span.imso_g, div.imso-hide-overflow, span.imso-fp")

                if len(teams) >= 2:
                    home = teams[0].text.strip()
                    away = teams[1].text.strip()
                    match_key = f"{home} - {away}"

                    status = status_elem.text.strip() if status_elem else "Bekliyor"
                    
                    if len(scores) >= 2:
                        score_text = f"{scores[0].text.strip()} - {scores[1].text.strip()}"
                    else:
                        score_text = "0 - 0"

                    matches[match_key] = {
                        "match_name": match_key,
                        "home": home,
                        "away": away,
                        "score": score_text,
                        "status": status
                    }
            except Exception:
                continue

    except Exception as e:
        print(f"⚠️ Canlı tarama hatası: {e}")

    return matches

async def monitor_matches():
    global TRACKED_MATCHES
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"] # Render uyumluluk parametreleri
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="tr-TR"
        )
        page = await context.new_page()

        print("🚀 Render üzerinde canlı maç takip motoru başladı...")

        current_data = await fetch_live_matches(page)
        
        if current_data:
            TRACKED_MATCHES = current_data
            
            init_msg = "📊 *GÜNÜN MAÇLARI VE CANLI TAKİP BÜLTENİ*\n"
            init_msg += f"📅 *{datetime.datetime.now().strftime('%d Eylül %Y')}*\n\n"
            init_msg += f"🤖 Toplam *{len(TRACKED_MATCHES)}* maç takibe alındı:\n\n"
            
            for m_key, m_val in TRACKED_MATCHES.items():
                init_msg += f"⚽ *MAÇ:* {m_val['match_name']}\n"
                init_msg += f"⏰ Durum: {m_val['status']} | Skor: {m_val['score']}\n\n"
                
            send_telegram_message(init_msg)

        while True:
            await asyncio.sleep(60)
            print(f"🔄 [{datetime.datetime.now().strftime('%H:%M:%S')}] Kontrol ediliyor...")
            
            live_data = await fetch_live_matches(page)
            
            for m_key, new_info in live_data.items():
                if m_key in TRACKED_MATCHES:
                    old_info = TRACKED_MATCHES[m_key]
                    match_title = new_info['match_name']
                    
                    # 1. GOL
                    if old_info["score"] != new_info["score"] and new_info["score"] != "0 - 0":
                        alert = f"⚽ *GOOOOOLLLL!*\n\n"
                        alert += f"🏟️ *MAÇ:* {match_title}\n"
                        alert += f"🔥 Yeni Skor: *{new_info['score']}*\n"
                        alert += f"⏱️ Anlık Durum: {new_info['status']}"
                        send_telegram_message(alert)
                    
                    # 2. İLK YARI BİTTİ
                    if ("İY" in new_info["status"] or "Devre Arası" in new_info["status"]) and ("İY" not in old_info["status"] and "Devre Arası" not in old_info["status"]):
                        alert = f"⏸️ *İLK YARI BİTTİ*\n\n"
                        alert += f"🏟️ *MAÇ:* {match_title}\n"
                        alert += f"📊 İlk Yarı Skoru: *{new_info['score']}*"
                        send_telegram_message(alert)

                    # 3. İKİNCİ YARI BAŞLADI
                    if ("2.Y" in new_info["status"] or "46'" in new_info["status"]) and ("İY" in old_info["status"] or "Devre Arası" in old_info["status"]):
                        alert = f"▶️ *İKİNCİ YARI BAŞLADI*\n\n"
                        alert += f"🏟️ *MAÇ:* {match_title}\n"
                        alert += f"📊 Skor: *{new_info['score']}*"
                        send_telegram_message(alert)

                    # 4. MAÇ BİTTİ
                    if ("MS" in new_info["status"] or "Bitti" in new_info["status"]) and ("MS" not in old_info["status"] and "Bitti" not in old_info["status"]):
                        alert = f"🏁 *MAÇ BİTTİ*\n\n"
                        alert += f"🏟️ *MAÇ:* {match_title}\n"
                        alert += f"🏆 Maç Sonucu: *{new_info['score']}*"
                        send_telegram_message(alert)

                    TRACKED_MATCHES[m_key] = new_info

        await browser.close()

if __name__ == "__main__":
    asyncio.run(monitor_matches())
