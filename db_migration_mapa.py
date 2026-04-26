import toml
import psycopg2

secrets_path = ".streamlit/secrets.toml"
secrets = toml.load(secrets_path)
p = secrets["postgres"]

print(f"Connecting to {p['host']}...")
conn = psycopg2.connect(
    host=p["host"],
    port=p.get("port", 5432),
    database=p["database"],
    user=p["user"],
    password=p["password"]
)

conn.autocommit = True
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE mapa_relacionamiento ADD COLUMN telefono TEXT;")
    print("Added telefono to mapa_relacionamiento.")
except Exception as e:
    print(f"Error adding telefono: {e}")

try:
    cur.execute("""
CREATE TABLE IF NOT EXISTS interacciones_mapa_relacionamiento (
    id BIGSERIAL PRIMARY KEY,
    contacto_id BIGINT NOT NULL REFERENCES mapa_relacionamiento(id) ON DELETE CASCADE,
    fecha DATE NOT NULL,
    tipo TEXT,
    resultado TEXT,
    observaciones TEXT,
    created_by BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
    """)
    print("Created table interacciones_mapa_relacionamiento.")
except Exception as e:
    print(f"Error creating table: {e}")

cur.close()
conn.close()
print("Done.")
