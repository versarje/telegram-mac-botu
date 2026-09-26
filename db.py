import pymysql
import config

def db_baglan():
    return pymysql.connect(
        host=config.MYSQL_HOST,
        port=config.MYSQL_PORT,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
        db=config.MYSQL_DB,
        charset="utf8mb4",
        connect_timeout=10,
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor
    )

def tablo_kur():
    """Uygulama ayağa kalktığında tablo yoksa oluşturur."""
    try:
        conn = db_baglan()
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tahminler (
                    match_id VARCHAR(50) PRIMARY KEY,
                    mac VARCHAR(150),
                    lig VARCHAR(100),
                    saat VARCHAR(20),
                    tahmin VARCHAR(50),
                    tur VARCHAR(20),
                    skor VARCHAR(20) DEFAULT '0-0',
                    durum VARCHAR(50) DEFAULT '⏳ BEKLENİYOR',
                    tarih VARCHAR(20)
                );
            """)
        conn.close()
        print("✅ MySQL Tablosu Hazır.")
    except Exception as e:
        print("❌ [MYSQL TABLO HATA]:", e)
