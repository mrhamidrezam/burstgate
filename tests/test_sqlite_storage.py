import os
import tempfile
import time
import pytest
from burstgate.storage.sqlite import SQLiteStorage
from burstgate.algorithms.token_bucket import TokenBucket


def test_sqlite_storage_crud():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_limits.db")
        storage = SQLiteStorage(db_path=db_path)

        # Set and get
        storage.set("foo", {"count": 42}, ttl=10.0)
        val = storage.get("foo")
        assert val == {"count": 42}

        # Atomic update
        def increment(state):
            c = state.get("count", 0) if state else 0
            return {"count": c + 1}, c + 1

        result = storage.atomic_update("foo", increment)
        assert result == 43
        assert storage.get("foo") == {"count": 43}

        # Delete
        assert storage.delete("foo") is True
        assert storage.get("foo") is None

        storage.close()


def test_sqlite_storage_with_token_bucket():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "tb_limits.db")
        storage = SQLiteStorage(db_path=db_path)
        tb = TokenBucket(rate=10, capacity=10, storage=storage, key="user:123")

        assert tb.consume(5)[0] is True
        assert tb.consume(5)[0] is True
        assert tb.consume(1)[0] is False

        storage.close()
