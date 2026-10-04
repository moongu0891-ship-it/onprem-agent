> 측정 장소: Claude 클라우드 작업 환경(CPU, Python 3.13). 모델을 내려받지 않는 해시 임베더·BM25 로만 잰 기준선이며, CI 회귀 검사도 같은 설정으로 돈다.

# 검색 평가: retrieval_baseline

- 실행: 2026-10-04T03:07:41+00:00 · Python 3.13.16 · x86_64
- 청킹: 최대 600자, 겹침 80자

## 시나리오: ops (청크 45개, 질문 37개)

| 갈래 | R@1 | R@3 | R@5 | MRR | 코드 R@3 | 바꿔 말하기 R@3 | 어려운 R@3 | 색인(s) | p50(ms) | p95(ms) |
|---|---|---|---|---|---|---|---|---|---|---|
| bm25 | 0.78 | 0.89 | 0.89 | 0.83 | 1.00 | 1.00 | 0.50 | 2.45 | 0.6 | 0.8 |
| dense(hash·memory) | 0.38 | 0.68 | 0.81 | 0.55 | 0.77 | 0.75 | 0.38 | 0.04 | 0.1 | 0.3 |
| dense(hash·chroma) | 0.38 | 0.68 | 0.81 | 0.55 | 0.77 | 0.75 | 0.38 | 0.02 | 2.3 | 2.8 |
| hybrid(bm25+hash) | 0.76 | 0.89 | 0.89 | 0.81 | 1.00 | 1.00 | 0.50 | 0.17 | 0.7 | 0.9 |
| hybrid-w(bm25 0.3+hash 1.0) | 0.65 | 0.84 | 0.89 | 0.74 | 0.92 | 0.94 | 0.50 | 0.18 | 0.6 | 0.9 |
| routed(code→hybrid, else hash) | 0.62 | 0.76 | 0.86 | 0.70 | 1.00 | 0.75 | 0.38 | 0.15 | 0.2 | 0.7 |

저장소 비교 (모든 저장소가 같은 벡터·같은 HNSW 설정을 씀. 근사 재현율 = 전수 비교 상위 10개를 되찾은 비율, 1.00 이 정확)

| 갈래 | 근사 재현율@10 | 임베딩(s) | 저장소 적재(s) | DB 검색 p50(ms) | DB 검색 p95(ms) |
|---|---|---|---|---|---|
| dense(hash·memory) | 1.00 | 0.04 | 0.00 | 0.02 | 0.07 |
| dense(hash·chroma) | 1.00 | 0.00 | 0.02 | 2.19 | 2.53 |

<details><summary>bm25 — 상위 3개에서 놓친 질문 4개</summary>

- `ops-h02` 정답 ['ERR-301'] → 상위 3: []
- `ops-h04` 정답 ['OPS-DRF-08'] → 상위 3: ['OPS-CRB-03', 'OPS-CRB-08', 'OPS-CRB-04']
- `ops-h06` 정답 ['OPS-STR'] → 상위 3: ['OPS-CRB-03', 'OPS-CRB-04', 'OPS-CRB-05']
- `ops-h07` 정답 ['OPS-CAL'] → 상위 3: ['OPS-SAFE', 'OPS-RST', 'OPS-OVR']

</details>

<details><summary>dense(hash·memory) — 상위 3개에서 놓친 질문 12개</summary>

- `ops-c02` 정답 ['OPS-CRB-06'] → 상위 3: ['OPS-SAFE', 'OPS-CRB-01', 'OPS-CRB-02']
- `ops-c09` 정답 ['OPS-LVL-05'] → 상위 3: ['OPS-SAFE', 'OPS-DRF-02', 'OPS-LVL-02']
- `ops-c10` 정답 ['OPS-SPK-02'] → 상위 3: ['OPS-SAFE', 'OPS-DRF-02', 'OPS-DRF-01']
- `ops-p04` 정답 ['ERR-302'] → 상위 3: ['OPS-LVL-03', 'OPS-LVL-05', 'OPS-SPK-03']
- `ops-p06` 정답 ['OPS-CRB-03'] → 상위 3: ['OPS-SPK-06', 'OPS-SPK-05', 'ERR-302']
- `ops-p07` 정답 ['OPS-DRF-08'] → 상위 3: ['OPS-SPK-08', 'ERR-301', 'OPS-SPK-04']
- `ops-p13` 정답 ['OPS-RST'] → 상위 3: ['OPS-LVL-06', 'OPS-LVL-05', 'OPS-LVL-02']
- `ops-h01` 정답 ['OPS-SAFE'] → 상위 3: ['OPS-LVL-04', 'OPS-LVL-03', 'OPS-LVL-05']
- `ops-h02` 정답 ['ERR-301'] → 상위 3: ['OPS-DRF-06', 'OPS-DRF-02', 'OPS-CRB-02']
- `ops-h04` 정답 ['OPS-DRF-08'] → 상위 3: ['OPS-LVL-01', 'OPS-DRF-01', 'OPS-LVL-07']
- `ops-h06` 정답 ['OPS-STR'] → 상위 3: ['OPS-SPK-03', 'OPS-SPK-04', 'OPS-DRF-03']
- `ops-h07` 정답 ['OPS-CAL'] → 상위 3: ['OPS-SAFE', 'OPS-LVL-05', 'OPS-LVL-06']

</details>

<details><summary>dense(hash·chroma) — 상위 3개에서 놓친 질문 12개</summary>

- `ops-c02` 정답 ['OPS-CRB-06'] → 상위 3: ['OPS-SAFE', 'OPS-CRB-01', 'OPS-CRB-02']
- `ops-c09` 정답 ['OPS-LVL-05'] → 상위 3: ['OPS-SAFE', 'OPS-DRF-02', 'OPS-LVL-02']
- `ops-c10` 정답 ['OPS-SPK-02'] → 상위 3: ['OPS-SAFE', 'OPS-DRF-02', 'OPS-DRF-01']
- `ops-p04` 정답 ['ERR-302'] → 상위 3: ['OPS-LVL-03', 'OPS-LVL-05', 'OPS-SPK-03']
- `ops-p06` 정답 ['OPS-CRB-03'] → 상위 3: ['OPS-SPK-06', 'OPS-SPK-05', 'ERR-302']
- `ops-p07` 정답 ['OPS-DRF-08'] → 상위 3: ['OPS-SPK-08', 'ERR-301', 'OPS-SPK-04']
- `ops-p13` 정답 ['OPS-RST'] → 상위 3: ['OPS-LVL-06', 'OPS-LVL-05', 'OPS-LVL-02']
- `ops-h01` 정답 ['OPS-SAFE'] → 상위 3: ['OPS-LVL-04', 'OPS-LVL-03', 'OPS-LVL-05']
- `ops-h02` 정답 ['ERR-301'] → 상위 3: ['OPS-DRF-06', 'OPS-DRF-02', 'OPS-CRB-02']
- `ops-h04` 정답 ['OPS-DRF-08'] → 상위 3: ['OPS-LVL-01', 'OPS-DRF-01', 'OPS-LVL-07']
- `ops-h06` 정답 ['OPS-STR'] → 상위 3: ['OPS-SPK-03', 'OPS-SPK-04', 'OPS-DRF-03']
- `ops-h07` 정답 ['OPS-CAL'] → 상위 3: ['OPS-SAFE', 'OPS-LVL-05', 'OPS-LVL-06']

</details>

<details><summary>hybrid(bm25+hash) — 상위 3개에서 놓친 질문 4개</summary>

- `ops-h02` 정답 ['ERR-301'] → 상위 3: ['OPS-DRF-06', 'OPS-DRF-02', 'OPS-CRB-02']
- `ops-h04` 정답 ['OPS-DRF-08'] → 상위 3: ['OPS-CRB-01', 'OPS-CRB-07', 'OPS-CRB-03']
- `ops-h06` 정답 ['OPS-STR'] → 상위 3: ['OPS-CRB-03', 'OPS-CRB-04', 'OPS-DRF-03']
- `ops-h07` 정답 ['OPS-CAL'] → 상위 3: ['OPS-SAFE', 'OPS-RST', 'OPS-LVL-05']

</details>

<details><summary>hybrid-w(bm25 0.3+hash 1.0) — 상위 3개에서 놓친 질문 6개</summary>

- `ops-c09` 정답 ['OPS-LVL-05'] → 상위 3: ['OPS-DRF-02', 'OPS-DRF-01', 'OPS-LVL-02']
- `ops-p06` 정답 ['OPS-CRB-03'] → 상위 3: ['ERR-302', 'OPS-CRB-05', 'OPS-SPK-05']
- `ops-h02` 정답 ['ERR-301'] → 상위 3: ['OPS-DRF-06', 'OPS-DRF-02', 'OPS-CRB-02']
- `ops-h04` 정답 ['OPS-DRF-08'] → 상위 3: ['OPS-CRB-01', 'OPS-CRB-07', 'OPS-LVL-01']
- `ops-h06` 정답 ['OPS-STR'] → 상위 3: ['OPS-SPK-03', 'OPS-DRF-03', 'OPS-SPK-04']
- `ops-h07` 정답 ['OPS-CAL'] → 상위 3: ['OPS-SAFE', 'OPS-LVL-05', 'OPS-RST']

</details>

<details><summary>routed(code→hybrid, else hash) — 상위 3개에서 놓친 질문 9개</summary>

- `ops-p04` 정답 ['ERR-302'] → 상위 3: ['OPS-LVL-03', 'OPS-LVL-05', 'OPS-SPK-03']
- `ops-p06` 정답 ['OPS-CRB-03'] → 상위 3: ['OPS-SPK-06', 'OPS-SPK-05', 'ERR-302']
- `ops-p07` 정답 ['OPS-DRF-08'] → 상위 3: ['OPS-SPK-08', 'ERR-301', 'OPS-SPK-04']
- `ops-p13` 정답 ['OPS-RST'] → 상위 3: ['OPS-LVL-06', 'OPS-LVL-05', 'OPS-LVL-02']
- `ops-h01` 정답 ['OPS-SAFE'] → 상위 3: ['OPS-LVL-04', 'OPS-LVL-03', 'OPS-LVL-05']
- `ops-h02` 정답 ['ERR-301'] → 상위 3: ['OPS-DRF-06', 'OPS-DRF-02', 'OPS-CRB-02']
- `ops-h04` 정답 ['OPS-DRF-08'] → 상위 3: ['OPS-LVL-01', 'OPS-DRF-01', 'OPS-LVL-07']
- `ops-h06` 정답 ['OPS-STR'] → 상위 3: ['OPS-SPK-03', 'OPS-SPK-04', 'OPS-DRF-03']
- `ops-h07` 정답 ['OPS-CAL'] → 상위 3: ['OPS-SAFE', 'OPS-LVL-05', 'OPS-LVL-06']

</details>

## 시나리오: cs (청크 23개, 질문 31개)

| 갈래 | R@1 | R@3 | R@5 | MRR | 코드 R@3 | 바꿔 말하기 R@3 | 어려운 R@3 | 색인(s) | p50(ms) | p95(ms) |
|---|---|---|---|---|---|---|---|---|---|---|
| bm25 | 0.81 | 0.87 | 0.87 | 0.87 | 1.00 | 0.93 | 0.62 | 0.03 | 0.3 | 0.5 |
| dense(hash·memory) | 0.52 | 0.81 | 0.85 | 0.68 | 1.00 | 0.83 | 0.56 | 0.01 | 0.1 | 0.2 |
| dense(hash·chroma) | 0.52 | 0.81 | 0.85 | 0.68 | 1.00 | 0.83 | 0.56 | 0.02 | 2.1 | 2.7 |
| hybrid(bm25+hash) | 0.77 | 0.84 | 0.89 | 0.86 | 1.00 | 0.93 | 0.50 | 0.03 | 0.5 | 0.8 |
| hybrid-w(bm25 0.3+hash 1.0) | 0.58 | 0.82 | 0.82 | 0.72 | 1.00 | 0.90 | 0.50 | 0.03 | 0.5 | 0.7 |
| routed(code→hybrid, else hash) | 0.52 | 0.81 | 0.85 | 0.68 | 1.00 | 0.83 | 0.56 | 0.03 | 0.1 | 0.5 |

저장소 비교 (모든 저장소가 같은 벡터·같은 HNSW 설정을 씀. 근사 재현율 = 전수 비교 상위 10개를 되찾은 비율, 1.00 이 정확)

| 갈래 | 근사 재현율@10 | 임베딩(s) | 저장소 적재(s) | DB 검색 p50(ms) | DB 검색 p95(ms) |
|---|---|---|---|---|---|
| dense(hash·memory) | 1.00 | 0.01 | 0.00 | 0.01 | 0.04 |
| dense(hash·chroma) | 1.00 | 0.00 | 0.02 | 1.91 | 2.48 |

<details><summary>bm25 — 상위 3개에서 놓친 질문 5개</summary>

- `cs-p06` 정답 ['FAQ-02', 'CS-PLN-5T34'] → 상위 3: ['FAQ-02', 'CS-CHG', 'CS-OVR']
- `cs-p12` 정답 ['FAQ-03', 'CS-PLN-LS25'] → 상위 3: ['FAQ-03', 'FAQ-02', 'CS-CHG']
- `cs-h03` 정답 ['CS-LOST'] → 상위 3: []
- `cs-h04` 정답 ['CS-UNPAID'] → 상위 3: ['CS-PRIV', 'CS-TRANS', 'CS-LOST']
- `cs-h08` 정답 ['FAQ-03', 'CS-PLN-LS25'] → 상위 3: ['CS-OVR', 'CS-ROAM', 'FAQ-02']

</details>

<details><summary>dense(hash·memory) — 상위 3개에서 놓친 질문 7개</summary>

- `cs-p03` 정답 ['CS-LOST'] → 상위 3: ['FAQ-02', 'CS-OVR', 'CS-SHARE']
- `cs-p04` 정답 ['CS-UNPAID'] → 상위 3: ['FAQ-03', 'CS-TRANS', 'CS-ROAM']
- `cs-p06` 정답 ['FAQ-02', 'CS-PLN-5T34'] → 상위 3: ['CS-CHG', 'FAQ-02', 'CS-UNPAID']
- `cs-h03` 정답 ['CS-LOST'] → 상위 3: ['CS-ADD', 'CS-ROAM', 'CS-TRANS']
- `cs-h04` 정답 ['CS-UNPAID'] → 상위 3: ['CS-TRANS', 'CS-LOST', 'CS-PAUSE']
- `cs-h06` 정답 ['CS-OVR'] → 상위 3: ['CS-TRANS', 'CS-UNPAID', 'CS-PAUSE']
- `cs-h08` 정답 ['FAQ-03', 'CS-PLN-LS25'] → 상위 3: ['CS-PLN-LT33', 'FAQ-03', 'CS-CHG']

</details>

<details><summary>dense(hash·chroma) — 상위 3개에서 놓친 질문 7개</summary>

- `cs-p03` 정답 ['CS-LOST'] → 상위 3: ['FAQ-02', 'CS-OVR', 'CS-SHARE']
- `cs-p04` 정답 ['CS-UNPAID'] → 상위 3: ['FAQ-03', 'CS-TRANS', 'CS-ROAM']
- `cs-p06` 정답 ['FAQ-02', 'CS-PLN-5T34'] → 상위 3: ['CS-CHG', 'FAQ-02', 'CS-UNPAID']
- `cs-h03` 정답 ['CS-LOST'] → 상위 3: ['CS-ADD', 'CS-ROAM', 'CS-TRANS']
- `cs-h04` 정답 ['CS-UNPAID'] → 상위 3: ['CS-TRANS', 'CS-LOST', 'CS-PAUSE']
- `cs-h06` 정답 ['CS-OVR'] → 상위 3: ['CS-TRANS', 'CS-UNPAID', 'CS-PAUSE']
- `cs-h08` 정답 ['FAQ-03', 'CS-PLN-LS25'] → 상위 3: ['CS-PLN-LT33', 'FAQ-03', 'CS-CHG']

</details>

<details><summary>hybrid(bm25+hash) — 상위 3개에서 놓친 질문 6개</summary>

- `cs-p06` 정답 ['FAQ-02', 'CS-PLN-5T34'] → 상위 3: ['FAQ-02', 'CS-CHG', 'CS-UNPAID']
- `cs-p12` 정답 ['FAQ-03', 'CS-PLN-LS25'] → 상위 3: ['FAQ-03', 'FAQ-01', 'CS-PLN-LT49']
- `cs-h03` 정답 ['CS-LOST'] → 상위 3: ['CS-ADD', 'CS-ROAM', 'CS-TRANS']
- `cs-h04` 정답 ['CS-UNPAID'] → 상위 3: ['CS-TRANS', 'CS-LOST', 'CS-PRIV']
- `cs-h06` 정답 ['CS-OVR'] → 상위 3: ['CS-CHG', 'CS-PAUSE', 'CS-ROAM']
- `cs-h08` 정답 ['FAQ-03', 'CS-PLN-LS25'] → 상위 3: ['CS-ROAM', 'CS-OVR', 'FAQ-02']

</details>

<details><summary>hybrid-w(bm25 0.3+hash 1.0) — 상위 3개에서 놓친 질문 6개</summary>

- `cs-p04` 정답 ['CS-UNPAID'] → 상위 3: ['FAQ-03', 'CS-TRANS', 'CS-PLN-LS25']
- `cs-p06` 정답 ['FAQ-02', 'CS-PLN-5T34'] → 상위 3: ['CS-CHG', 'FAQ-02', 'CS-UNPAID']
- `cs-h03` 정답 ['CS-LOST'] → 상위 3: ['CS-ADD', 'CS-ROAM', 'CS-TRANS']
- `cs-h04` 정답 ['CS-UNPAID'] → 상위 3: ['CS-TRANS', 'CS-LOST', 'CS-PRIV']
- `cs-h06` 정답 ['CS-OVR'] → 상위 3: ['CS-CHG', 'CS-PAUSE', 'CS-ROAM']
- `cs-h08` 정답 ['FAQ-03', 'CS-PLN-LS25'] → 상위 3: ['CS-ROAM', 'CS-SHARE', 'FAQ-02']

</details>

<details><summary>routed(code→hybrid, else hash) — 상위 3개에서 놓친 질문 7개</summary>

- `cs-p03` 정답 ['CS-LOST'] → 상위 3: ['FAQ-02', 'CS-OVR', 'CS-SHARE']
- `cs-p04` 정답 ['CS-UNPAID'] → 상위 3: ['FAQ-03', 'CS-TRANS', 'CS-ROAM']
- `cs-p06` 정답 ['FAQ-02', 'CS-PLN-5T34'] → 상위 3: ['CS-CHG', 'FAQ-02', 'CS-UNPAID']
- `cs-h03` 정답 ['CS-LOST'] → 상위 3: ['CS-ADD', 'CS-ROAM', 'CS-TRANS']
- `cs-h04` 정답 ['CS-UNPAID'] → 상위 3: ['CS-TRANS', 'CS-LOST', 'CS-PAUSE']
- `cs-h06` 정답 ['CS-OVR'] → 상위 3: ['CS-TRANS', 'CS-UNPAID', 'CS-PAUSE']
- `cs-h08` 정답 ['FAQ-03', 'CS-PLN-LS25'] → 상위 3: ['CS-PLN-LT33', 'FAQ-03', 'CS-CHG']

</details>
