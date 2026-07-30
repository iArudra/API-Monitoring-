import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Postgres/TimescaleDB connection
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "centralwatch")
    DB_USER = os.getenv("DB_USER", "centralwatch")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    # Connection pool sizing. Keep MIN low for a student-project VM;
    # raise MAX if you see "pool exhausted" errors under load testing.
    DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "2"))
    DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))

    # Simple API key check for agents posting events (per-environment
    # keys keep this from being wide open). Comma-separated in .env,
    # e.g. AGENT_API_KEYS=dev:abc123,staging:def456,prod:ghi789
    AGENT_API_KEYS = os.getenv("AGENT_API_KEYS", "")

    @property
    def db_conninfo(self):
        return (
            f"host={self.DB_HOST} port={self.DB_PORT} dbname={self.DB_NAME} "
            f"user={self.DB_USER} password={self.DB_PASSWORD}"
        )

    @property
    def agent_keys_by_env(self):
        """Parses AGENT_API_KEYS into {env: key} dict."""
        pairs = [p for p in self.AGENT_API_KEYS.split(",") if p]
        out = {}
        for p in pairs:
            if ":" in p:
                env, key = p.split(":", 1)
                out[env.strip()] = key.strip()
        return out


config = Config()
