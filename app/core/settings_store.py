import psycopg2

SYNC_DB_URL = "postgresql://imagefactory:strongpassword@localhost:5432/imagefactory"

# Fallback defaults if a key is missing
DEFAULTS = {
    "active_model": "llama3.1:8b",
    "default_cpu": "2",
    "default_ram_gb": "4",
    "default_os": "Ubuntu 22.04",
    "maintenance_mode": "false",
}

def get_setting_sync(key: str, default=None):
    """Synchronous read — used by orchestrator/executor."""
    fallback = default if default is not None else DEFAULTS.get(key, "")
    try:
        conn = psycopg2.connect(SYNC_DB_URL)
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else fallback
    except Exception:
        return fallback