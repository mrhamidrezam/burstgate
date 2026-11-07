"""
Inter-Process Shared Rate Limiting with SQLiteStorage.
Multiple separate OS processes / workers coordinate limits without Redis!
"""

import os
from burstgate import RateLimiter, SQLiteStorage

db_path = "shared_limits.sqlite3"
storage = SQLiteStorage(db_path=db_path)

# Shared across workers: 10 requests per second total
limiter = RateLimiter(
    limit=10,
    period=1.0,
    storage=storage,
    key="api:shared_endpoint",
)

pid = os.getpid()
print(f"Worker PID {pid} acquiring permits from SQLite WAL storage...")

for i in range(5):
    with limiter.acquire(tokens=1):
        print(f"PID {pid} acquired permit #{i+1}")

storage.close()
if os.path.exists(db_path):
    for f in [db_path, f"{db_path}-wal", f"{db_path}-shm"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass
