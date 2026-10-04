# Elasticsearch + 한국어 형태소 분석기 Nori
ARG ES_VERSION=8.17.0
FROM docker.elastic.co/elasticsearch/elasticsearch:${ES_VERSION}
RUN bin/elasticsearch-plugin install --batch analysis-nori
