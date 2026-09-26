import re
import requests
import config

def telegram_post(metin, chat_id=None):
    target_chat = chat_id if chat_id else config.TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
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

def turkcelestir(metin, tur="takim"):
    if not metin:
        return "Bilinmiyor"
    
    sozluk = config.LIG_SOZLUK if tur == "lig" else config.TAKIM_SOZLUK
    for eng, tr in sozluk.items():
        if eng.lower() in metin.lower():
            return tr
            
    if tur == "takim":
        metin = re.sub(r'\b(FC|CF|BSC|FK|SK|SV|AC|SC)\b', '', metin, flags=re.IGNORECASE).strip()
        
    return metin

def metin_veya_sozlukten_al(data, *anahtarlar):
    if not data: return ""
    if isinstance(data, str): return data
    if isinstance(data, dict):
        for key in anahtarlar:
            val = data.get(key)
            if val:
                if isinstance(val, str): return val
                elif isinstance(val, dict):
                    res = val.get("name", val.get("text", ""))
                    if res: return str(res)
    return ""

def akilli_tahmin_uret(match_id, ev, dep):
    TAHMINLER = [
        ("⚽ 2.5 ÜST", "UST25"),
        ("🛡️ 2.5 ALT", "ALT25"),
        ("🤝 KG VAR", "KG_VAR")
    ]
    seed = len(ev) + len(dep) + int("".join([c for c in str(match_id) if c.isdigit()] or "1"))
    indeks = seed % len(TAHMINLER)
    return TAHMINLER[indeks]
