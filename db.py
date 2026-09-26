import sqlite3

def get_db_connection():
    try:
        conn = sqlite3.connect("maclar.db")
        conn.row_factory = sqlite3.Row  # Sözlük yapısında okuma sağlar
        return conn
    except Exception as e:
        print(f"❌ SQLite Bağlantı Hatası: {e}")
        return None

def init_db():
    """Veritabanını ve gerekli tabloları oluşturur."""
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
                    tahmin TEXT,
                    ev_skor INTEGER DEFAULT -1,
                    dep_skor INTEGER DEFAULT -1
                )
            """)
            conn.commit()
        except Exception as e:
            print(f"❌ Tablo Oluşturma Hatası: {e}")
        finally:
            conn.close()

# Uygulama başlarken tabloyu hazırla
init_db()
