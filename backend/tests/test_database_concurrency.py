"""文件 SQLite 的并发请求不能关闭另一个仍在使用的连接。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import text

from app.database import make_engine


def test_parallel_reads_keep_all_active_connections(tmp_path):
    engine = make_engine(tmp_path / "parallel.db")
    barrier = Barrier(8, timeout=10)

    def read(_):
        with engine.connect() as connection:
            barrier.wait()
            return connection.scalar(text("SELECT 1"))

    try:
        with ThreadPoolExecutor(max_workers=8) as workers:
            assert list(workers.map(read, range(8))) == [1] * 8
    finally:
        engine.dispose()
