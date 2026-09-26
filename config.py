import os

# API & Telegram
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "a218c708b2msh4439e269a1c67ebp1a33c8jsnb1f2b991cb2a")
RAPIDAPI_HOST = "free-api-live-football-data.p.rapidapi.com"
BASE_URL = f"https://{RAPIDAPI_HOST}"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8894398415:AAEY_ffz8iPL8qZ8vJq3bgat7cibeQFhvI8")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-1004461429503")


# Cloudflare D1 Ayarları
CLOUDFLARE_ACCOUNT_ID = "9d67b6866b5fbfb1bb8ae080c0e763e2"
CLOUDFLARE_DATABASE_ID = "bade913e-de57-4040-8245-f3f81016d8d7"
CLOUDFLARE_API_TOKEN = "Cfut_MYGDnjewSj3LweDH8zXSzKuGEQONYgbWg3rB1u8e5db58976"

# Sözlükler
LIG_SOZLUK = {
    "Premier League": "İngiltere Premier Lig",
    "LaLiga": "İspanya La Liga",
    "Serie A": "İtalya Serie A",
    "Bundesliga": "Almanya Bundesliga",
    "Ligue 1": "Fransa Ligue 1",
    "Super Lig": "Trendyol Süper Lig",
    "Eredivisie": "Hollanda Eredivisie",
    "Primeira Liga": "Portekiz Süper Ligi",
    "UEFA Champions League": "UEFA Şampiyonlar Ligi",
    "UEFA Europa League": "UEFA Avrupa Ligi",
    "UEFA Conference League": "UEFA Konferans Ligi",
    "Championship": "İngiltere Championship"
}

TAKIM_SOZLUK = {
    "Bayern München": "Bayern Münih",
    "Bayern Munich": "Bayern Münih",
    "Red Star Belgrade": "Kızılıldız",
    "Sporting CP": "Sporting Lizbon",
    "Athletic Club": "Athletic Bilbao",
    "Inter": "Inter Milan",
    "AC Milan": "Milan",
    "PSV Eindhoven": "PSV",
    "AZ Alkmaar": "AZ Alkmaar",
    "Köln": "Köln",
    "Nürnberg": "Nürnberg"
}
