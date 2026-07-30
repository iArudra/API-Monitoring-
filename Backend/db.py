"""
Connection pooling for TimescaleDB.

Why this matters: Flask's default request-per-thread model means every
request that opens its own fresh Postgres connection pays TCP + auth
handshake cost on top of the query itself. Under a few hundred events/sec
from three environments, that overhead alone can make ingestion the
bottleneck. A pool of pre-opened connections avoids that.
"""
from psycopg_pool import ConnectionPool
from config import config

_pool = None


def get_pool():
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=config.db_conninfo,
            min_size=config.DB_POOL_MIN,
            max_size=config.DB_POOL_MAX,
            open=True,
        )
    return _pool


def close_pool():
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
