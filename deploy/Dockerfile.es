# Elasticsearch + IK 中文分词插件
FROM elasticsearch:8.11.0

# 安装 IK 分析插件（infinilabs/analysis-ik，兼容 ES 8.x）
RUN elasticsearch-plugin install --batch https://get.infini.cloud/elasticsearch/analysis-ik/8.11.0
