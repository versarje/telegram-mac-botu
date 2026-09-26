import sqlite3

def get_db_connection():
    try:
        # SQLite proje dizininde maclar.db adında bir dosya oluşturur
        conn = sqlite3.connect("maclar.db")
        conn.row_factory = sqlite3.Row  # Verileri sözlük gibi okumayı sağlar
        return conn
    except Exception as e:
        print(f"❌ SQLite Bağlantı Hatası: {e}")
        return None

def init_db():
    """Veritabanı tablosu yoksa otomatik oluşturur."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS maclar (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    saat TEXT,
                    ev_sahibi TEXT,
                    deplasman TEXT,
                    lig TEXT,
                    tahmin TEXT
                )
            """)
            conn.commit()
        except Exception as e:
            print(f"❌ Tablo Oluşturma Hatası: {e}")
        finally:
            conn.close()

# Uygulama başladığında veritabanını ve tabloyu hazırla
init_db()
