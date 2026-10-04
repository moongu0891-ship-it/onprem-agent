# Elasticsearch + 한국어 형태소 분석기 Nori
# 파이썬 클라이언트(elasticsearch<9)와 주 버전을 맞춘다 — 9 클라이언트는 8 서버와 통신하지 못한다
ARG ES_VERSION=8.17.0
FROM docker.elastic.co/elasticsearch/elasticsearch:${ES_VERSION}
RUN bin/elasticsearch-plugin install --batch analysis-nori
