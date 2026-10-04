"""pgvector 어댑터. '이미 쓰는 PostgreSQL 에 확장 하나로 벡터 검색'이 되는지의 기준선.

에이전트의 상태 저장·SQL 도구도 PostgreSQL 을 쓰므로, 별도 벡터DB 없이 한 DB 로
끝낼 수 있는지가 운영 관점의 핵심 질문이다.
"""

from __future__ import annotations


class PgvectorStore:
    name = "pgvector"

    def __init__(self, dsn: str = "postgresql://agent:agent@localhost:5432/agent", table: str = "chunks",
                 hnsw_m: int = 16, ef_construct: int = 100, ef_search: int = 128):
        import psycopg
        from pgvector.psycopg import register_vector
        self.conn = psycopg.connect(dsn, autocommit=True)
        self.conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(self.conn)
        self.table = table
        self.hnsw = (hnsw_m, ef_construct)
        self.ef_search = ef_search

    def reset(self, dim: int) -> None:
        self.conn.execute(f"DROP TABLE IF EXISTS {self.table}")
        self.conn.execute(f"CREATE TABLE {self.table} (id text PRIMARY KEY, section_id text, embedding vector({dim}))")

    def add(self, ids, vectors, metadatas) -> None:
        with self.conn.cursor() as cur:
            with cur.copy(f"COPY {self.table} (id, section_id, embedding) FROM STDIN WITH (FORMAT BINARY)") as copy:
                copy.set_types(["text", "text", "vector"])
                for i, v, m in zip(ids, vectors, metadatas):
                    copy.write_row([i, m.get("section_id"), v])
        # 데이터를 다 넣은 뒤 인덱스를 만드는 편이 빠르다
        self.conn.execute(f"CREATE INDEX ON {self.table} USING hnsw (embedding vector_cosine_ops) "
                          f"WITH (m = {self.hnsw[0]}, ef_construction = {self.hnsw[1]})")
        self.conn.execute(f"SET hnsw.ef_search = {self.ef_search}")

    def search(self, vector, k):
        rows = self.conn.execute(
            f"SELECT id, 1 - (embedding <=> %s) AS sim FROM {self.table} ORDER BY embedding <=> %s LIMIT %s",
            (vector, vector, k)).fetchall()
        return [(r[0], float(r[1])) for r in rows]

    def __del__(self):
        try:
            self.conn.close()
        except Exception:
            pass
