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
    cur.execute("ALTER TABLE reuniones ADD COLUMN necesita_cobertura BOOLEAN DEFAULT FALSE;")
    print("Added necesita_cobertura.")
except Exception as e:
    print(f"Error adding necesita_cobertura: {e}")

try:
    cur.execute("ALTER TABLE reuniones ADD COLUMN realizada BOOLEAN DEFAULT NULL;")
    print("Added realizada.")
except Exception as e:
    print(f"Error adding realizada: {e}")

cur.close()
conn.close()
print("Done.")
