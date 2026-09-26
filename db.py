import pymysql
import config

def get_db_connection():
    """MySQL veritabanına bağlantı sağlar."""
    try:
        return pymysql.connect(
            host=config.MYSQL_HOST,
            port=int(config.MYSQL_PORT),
            user=config.MYSQL_USER,
            password=config.MYSQL_PASSWORD,
            db=config.MYSQL_DB,
            charset="utf8mb4",
            connect_timeout=10,
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        print("❌ DB Bağlantı Hatası:", e)
        return None

def tablo_kur():
    """Uygulama başladığında maclar tablosunu oluşturur."""
    conn = get_db_connection()
    if not conn:
        print("❌ Tablo kurulamadı: DB Bağlantısı yok.")
        return
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS maclar (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    saat VARCHAR(20),
                    ev_sahibi VARCHAR(150),
                    deplasman VARCHAR(150),
                    lig VARCHAR(100),
                    tahmin VARCHAR(50)
                );
            """)
        print("✅ MySQL Tablosu Hazır.")
    except Exception as e:
        print("❌ TABLO OLUSTURMA HATASI:", e)
    finally:
        conn.close()
