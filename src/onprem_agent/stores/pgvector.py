"""pgvector 어댑터. '이미 쓰는 PostgreSQL 에 확장 하나로 벡터 검색'이 되는지의 기준선.

에이전트의 상태 저장·SQL 도구도 PostgreSQL 을 쓰므로, 별도 벡터DB 없이 한 DB 로
끝낼 수 있는지가 운영 관점의 핵심 질문이다.
"""

from __future__ import annotations


class PgvectorStore:
    name = "pgvector"

    def __init__(self, dsn: str = "postgresql://agent:agent@localhost:5432/agent", table: str = "chunks",
                 hnsw_m: int = 16, ef_construct: int = 100, ef_search: int = 128, iterative_scan: bool = False,
                 force_index: bool = False):
        import psycopg
        from pgvector.psycopg import register_vector
        self.conn = psycopg.connect(dsn, autocommit=True)
        self.conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(self.conn)
        self.table = table
        self.hnsw = (hnsw_m, ef_construct)
        self.ef_search = ef_search
        # pgvector 의 HNSW 는 기본적으로 '근사 탐색 후 WHERE 로 거른다'. 거르고 나면 k 개보다 적게 남을 수 있다.
        # 0.8 부터 iterative_scan 으로 부족하면 더 탐색한다 — 필터 검색 비교의 핵심 축.
        self.iterative_scan = iterative_scan
        # 작은 표에서 필터를 걸면 PostgreSQL 플래너는 HNSW 대신 '골라서 전부 비교'를 택한다(정확하지만 커지면 느려짐).
        # force_index 는 데이터가 커져 인덱스를 쓰게 되는 상황을 미리 재현한다.
        self.force_index = force_index

    def reset(self, dim: int) -> None:
        self.conn.execute(f"DROP TABLE IF EXISTS {self.table}")
        self.conn.execute(f"CREATE TABLE {self.table} (id text PRIMARY KEY, section_id text, doc_type text, "
                          f"embedding vector({dim}))")

    def add(self, ids, vectors, metadatas) -> None:
        with self.conn.cursor() as cur:
            with cur.copy(f"COPY {self.table} (id, section_id, doc_type, embedding) FROM STDIN WITH (FORMAT BINARY)") as copy:
                copy.set_types(["text", "text", "text", "vector"])
                for i, v, m in zip(ids, vectors, metadatas):
                    copy.write_row([i, m.get("section_id"), m.get("doc_type"), v])
        # 데이터를 다 넣은 뒤 인덱스를 만드는 편이 빠르다
        self.conn.execute(f"CREATE INDEX ON {self.table} USING hnsw (embedding vector_cosine_ops) "
                          f"WITH (m = {self.hnsw[0]}, ef_construction = {self.hnsw[1]})")
        self.conn.execute(f"SET hnsw.ef_search = {self.ef_search}")
        if self.force_index:
            self.conn.execute("SET enable_seqscan = off")
        if self.iterative_scan:
            try:
                self.conn.execute("SET hnsw.iterative_scan = relaxed_order")
            except Exception as e:
                raise RuntimeError("iterative_scan 은 pgvector 0.8 이상에서만 된다") from e

    def search(self, vector, k, filter=None):
        where, params = "", []
        if filter:
            where = "WHERE " + " AND ".join(f"{f} = %s" for f in filter)
            params = list(filter.values())
        rows = self.conn.execute(
            f"SELECT id, 1 - (embedding <=> %s) AS sim FROM {self.table} {where} ORDER BY embedding <=> %s LIMIT %s",
            (vector, *params, vector, k)).fetchall()
        return [(r[0], float(r[1])) for r in rows]

    def __del__(self):
        try:
            self.conn.close()
        except Exception:
            pass
