import os

# API & Telegram
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "a218c708b2msh4439e269a1c67ebp1a33c8jsnb1f2b991cb2a")
RAPIDAPI_HOST = "free-api-live-football-data.p.rapidapi.com"
BASE_URL = f"https://{RAPIDAPI_HOST}"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8894398415:AAEY_ffz8iPL8qZ8vJq3bgat7cibeQFhvI8")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-1004461429503")

# Aiven MySQL
MYSQL_HOST = "mysql-2d07f53d-umuttopal51-ec18.e.aivencloud.com"
MYSQL_PORT = 21611
MYSQL_USER = "avnadmin"
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "AVNS_H5i1d0aVTmZE1CfZZrQ")
MYSQL_DB = "defaultdb"

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
