import requests
import config

D1_URL = f"https://api.cloudflare.com/client/v4/accounts/{config.CLOUDFLARE_ACCOUNT_ID}/d1/database/{config.CLOUDFLARE_DATABASE_ID}/query"

HEADERS = {
    "Authorization": f"Bearer {config.CLOUDFLARE_API_TOKEN}",
    "Content-Type": "application/json"
}

def execute_d1(sql, params=None):
    """Cloudflare D1 SQL sorgularını REST API üzerinden çalıştırır."""
    payload = {
        "sql": sql,
        "params": params or []
    }
    
    try:
        response = requests.post(D1_URL, headers=HEADERS, json=payload, timeout=15)
        res_json = response.json()
        
        if res_json.get("success"):
            result_data = res_json.get("result", [])
            if result_data and len(result_data) > 0:
                results = result_data[0].get("results", [])
                return results
            return []
        else:
            print(f"❌ D1 Hata: {res_json.get('errors')}")
            return None
    except Exception as e:
        print(f"❌ D1 Bağlantı Hatası: {e}")
        return None

def init_d1_db():
    """D1 üzerinde maclar tablosunu oluşturur."""
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS maclar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        saat TEXT,
        ev_sahibi TEXT,
        deplasman TEXT,
        lig TEXT,
        tahmin TEXT,
        ev_skor INTEGER DEFAULT NULL,
        dep_skor INTEGER DEFAULT NULL
    );
    """
    execute_d1(create_table_sql)
