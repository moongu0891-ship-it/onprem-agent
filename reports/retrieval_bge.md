# 검색 평가: retrieval_bge

- 실행: 2026-10-04T02:34:10+00:00 · Python 3.12.3 · x86_64
- 측정 장비: 노트북 RTX 5070 Laptop 8GB · WSL2 Ubuntu 24.04 (bge-m3 는 GPU 에서 실행)
- 청킹: 최대 600자, 겹침 80자

## 시나리오: ops (청크 45개, 질문 37개)

| 갈래 | R@1 | R@3 | R@5 | MRR | 코드 R@3 | 바꿔 말하기 R@3 | 어려운 R@3 | 색인(s) | p50(ms) | p95(ms) |
|---|---|---|---|---|---|---|---|---|---|---|
| bm25 | 0.78 | 0.89 | 0.89 | 0.83 | 1.00 | 1.00 | 0.50 | 1.56 | 0.2 | 0.3 |
| dense(bge-m3·memory) | 0.89 | 0.95 | 1.00 | 0.93 | 1.00 | 1.00 | 0.75 | 1.69 | 12.2 | 27.3 |
| dense(bge-m3·chroma) | 0.89 | 0.95 | 1.00 | 0.93 | 1.00 | 1.00 | 0.75 | 1.05 | 13.8 | 22.7 |
| hybrid(bm25+bge-m3) | 0.89 | 0.92 | 0.92 | 0.92 | 1.00 | 1.00 | 0.62 | 1.16 | 12.8 | 14.6 |
| hybrid-w(bm25 0.3+bge-m3 1.0) | 0.84 | 0.92 | 0.92 | 0.89 | 1.00 | 1.00 | 0.62 | 1.12 | 14.4 | 26.9 |
| routed(code→hybrid, else bge-m3) | 0.89 | 0.95 | 1.00 | 0.93 | 1.00 | 1.00 | 0.75 | 2.15 | 13.2 | 19.1 |

<details><summary>bm25 — 상위 3개에서 놓친 질문 4개</summary>

- `ops-h02` 정답 ['ERR-301'] → 상위 3: []
- `ops-h04` 정답 ['OPS-DRF-08'] → 상위 3: ['OPS-CRB-03', 'OPS-CRB-08', 'OPS-CRB-04']
- `ops-h06` 정답 ['OPS-STR'] → 상위 3: ['OPS-CRB-03', 'OPS-CRB-04', 'OPS-CRB-05']
- `ops-h07` 정답 ['OPS-CAL'] → 상위 3: ['OPS-SAFE', 'OPS-RST', 'OPS-OVR']

</details>

<details><summary>dense(bge-m3·memory) — 상위 3개에서 놓친 질문 2개</summary>

- `ops-h05` 정답 ['OPS-SPK-07'] → 상위 3: ['OPS-SPK-08', 'OPS-LVL-08', 'OPS-CRB-08']
- `ops-h06` 정답 ['OPS-STR'] → 상위 3: ['OPS-DRF-03', 'OPS-DRF-04', 'OPS-SPK-03']

</details>

<details><summary>dense(bge-m3·chroma) — 상위 3개에서 놓친 질문 2개</summary>

- `ops-h05` 정답 ['OPS-SPK-07'] → 상위 3: ['OPS-SPK-08', 'OPS-LVL-08', 'OPS-CRB-08']
- `ops-h06` 정답 ['OPS-STR'] → 상위 3: ['OPS-DRF-03', 'OPS-DRF-04', 'OPS-SPK-03']

</details>

<details><summary>hybrid(bm25+bge-m3) — 상위 3개에서 놓친 질문 3개</summary>

- `ops-h04` 정답 ['OPS-DRF-08'] → 상위 3: ['OPS-CRB-08', 'OPS-CRB-04', 'OPS-CRB-03']
- `ops-h06` 정답 ['OPS-STR'] → 상위 3: ['OPS-DRF-03', 'OPS-CRB-03', 'OPS-CRB-04']
- `ops-h07` 정답 ['OPS-CAL'] → 상위 3: ['OPS-RST', 'OPS-SAFE', 'OPS-LVL-05']

</details>

<details><summary>hybrid-w(bm25 0.3+bge-m3 1.0) — 상위 3개에서 놓친 질문 3개</summary>

- `ops-h04` 정답 ['OPS-DRF-08'] → 상위 3: ['OPS-CRB-08', 'OPS-CRB-04', 'OPS-CRB-03']
- `ops-h06` 정답 ['OPS-STR'] → 상위 3: ['OPS-DRF-03', 'OPS-DRF-04', 'OPS-SPK-03']
- `ops-h07` 정답 ['OPS-CAL'] → 상위 3: ['OPS-RST', 'OPS-SAFE', 'OPS-DRF-06']

</details>

<details><summary>routed(code→hybrid, else bge-m3) — 상위 3개에서 놓친 질문 2개</summary>

- `ops-h05` 정답 ['OPS-SPK-07'] → 상위 3: ['OPS-SPK-08', 'OPS-LVL-08', 'OPS-CRB-08']
- `ops-h06` 정답 ['OPS-STR'] → 상위 3: ['OPS-DRF-03', 'OPS-DRF-04', 'OPS-SPK-03']

</details>

## 시나리오: cs (청크 23개, 질문 31개)

| 갈래 | R@1 | R@3 | R@5 | MRR | 코드 R@3 | 바꿔 말하기 R@3 | 어려운 R@3 | 색인(s) | p50(ms) | p95(ms) |
|---|---|---|---|---|---|---|---|---|---|---|
| bm25 | 0.81 | 0.87 | 0.87 | 0.87 | 1.00 | 0.93 | 0.62 | 0.02 | 0.2 | 0.3 |
| dense(bge-m3·memory) | 0.92 | 0.97 | 1.00 | 0.98 | 1.00 | 0.93 | 1.00 | 0.23 | 11.5 | 17.5 |
| dense(bge-m3·chroma) | 0.92 | 0.97 | 1.00 | 0.98 | 1.00 | 0.93 | 1.00 | 0.24 | 15.4 | 20.9 |
| hybrid(bm25+bge-m3) | 0.90 | 0.90 | 0.95 | 0.95 | 1.00 | 0.93 | 0.75 | 0.25 | 12.5 | 19.7 |
| hybrid-w(bm25 0.3+bge-m3 1.0) | 0.90 | 0.90 | 0.97 | 0.95 | 1.00 | 0.93 | 0.75 | 0.25 | 13.0 | 19.3 |
| routed(code→hybrid, else bge-m3) | 0.92 | 0.97 | 1.00 | 0.98 | 1.00 | 0.93 | 1.00 | 0.49 | 12.0 | 17.2 |

<details><summary>bm25 — 상위 3개에서 놓친 질문 5개</summary>

- `cs-p06` 정답 ['FAQ-02', 'CS-PLN-5T34'] → 상위 3: ['FAQ-02', 'CS-CHG', 'CS-OVR']
- `cs-p12` 정답 ['FAQ-03', 'CS-PLN-LS25'] → 상위 3: ['FAQ-03', 'FAQ-02', 'CS-CHG']
- `cs-h03` 정답 ['CS-LOST'] → 상위 3: []
- `cs-h04` 정답 ['CS-UNPAID'] → 상위 3: ['CS-PRIV', 'CS-TRANS', 'CS-LOST']
- `cs-h08` 정답 ['FAQ-03', 'CS-PLN-LS25'] → 상위 3: ['CS-OVR', 'CS-ROAM', 'FAQ-02']

</details>

<details><summary>dense(bge-m3·memory) — 상위 3개에서 놓친 질문 2개</summary>

- `cs-p06` 정답 ['FAQ-02', 'CS-PLN-5T34'] → 상위 3: ['FAQ-02', 'FAQ-03', 'CS-PLN-LS25']
- `cs-p12` 정답 ['FAQ-03', 'CS-PLN-LS25'] → 상위 3: ['FAQ-03', 'CS-SHARE', 'CS-CHG']

</details>

<details><summary>dense(bge-m3·chroma) — 상위 3개에서 놓친 질문 2개</summary>

- `cs-p06` 정답 ['FAQ-02', 'CS-PLN-5T34'] → 상위 3: ['FAQ-02', 'FAQ-03', 'CS-PLN-LS25']
- `cs-p12` 정답 ['FAQ-03', 'CS-PLN-LS25'] → 상위 3: ['FAQ-03', 'CS-SHARE', 'CS-CHG']

</details>

<details><summary>hybrid(bm25+bge-m3) — 상위 3개에서 놓친 질문 4개</summary>

- `cs-p06` 정답 ['FAQ-02', 'CS-PLN-5T34'] → 상위 3: ['FAQ-02', 'CS-SHARE', 'CS-CHG']
- `cs-p12` 정답 ['FAQ-03', 'CS-PLN-LS25'] → 상위 3: ['FAQ-03', 'CS-CHG', 'FAQ-01']
- `cs-h04` 정답 ['CS-UNPAID'] → 상위 3: ['CS-PRIV', 'CS-TRANS', 'CS-ADD']
- `cs-h08` 정답 ['FAQ-03', 'CS-PLN-LS25'] → 상위 3: ['FAQ-02', 'CS-SHARE', 'CS-OVR']

</details>

<details><summary>hybrid-w(bm25 0.3+bge-m3 1.0) — 상위 3개에서 놓친 질문 4개</summary>

- `cs-p06` 정답 ['FAQ-02', 'CS-PLN-5T34'] → 상위 3: ['FAQ-02', 'CS-SHARE', 'CS-PLN-LS25']
- `cs-p12` 정답 ['FAQ-03', 'CS-PLN-LS25'] → 상위 3: ['FAQ-03', 'CS-CHG', 'FAQ-01']
- `cs-h04` 정답 ['CS-UNPAID'] → 상위 3: ['CS-PRIV', 'CS-TRANS', 'CS-ADD']
- `cs-h08` 정답 ['FAQ-03', 'CS-PLN-LS25'] → 상위 3: ['FAQ-02', 'CS-SHARE', 'CS-ROAM']

</details>

<details><summary>routed(code→hybrid, else bge-m3) — 상위 3개에서 놓친 질문 2개</summary>

- `cs-p06` 정답 ['FAQ-02', 'CS-PLN-5T34'] → 상위 3: ['FAQ-02', 'FAQ-03', 'CS-PLN-LS25']
- `cs-p12` 정답 ['FAQ-03', 'CS-PLN-LS25'] → 상위 3: ['FAQ-03', 'CS-SHARE', 'CS-CHG']

</details>
