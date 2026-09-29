export const patterns: Record<string, RegExp> = {
  PostgreSQL: /\b(?:postgresql|postgres)\b/i,
  Python: /\bpython\b|^\s*(?:from \w+ import|def \w+\()/im,
  Docker: /\bdocker\b|^FROM\s+\S+/im,
  LangGraph: /\blanggraph\b|\bStateGraph\b/i,
  LangChain: /\blangchain\b/i,
  "Vector DB":
    /\b(?:pinecone|qdrant|chromadb|weaviate|pgvector|faiss)\b|vector\s*(?:db|database)|벡터\s*(?:데이터베이스|DB)/i,
  RAG: /\bRAG\b|retrieval.augmented/i,
  MCP: /\bMCP\b|model context protocol/i,
  SQL: /\bSQL\b|SELECT\s+\w+\s+FROM/i,
  PyTorch: /\bpytorch\b|\bimport torch\b/i,
  Airflow: /\bairflow\b/i,
  Spark: /\b(?:pyspark|spark)\b/i,
  AWS: /\b(?:AWS|boto3)\b/i,
  Kubernetes: /\b(?:kubernetes|kubectl|k8s)\b/i,
  MLflow: /\bmlflow\b/i,
};
