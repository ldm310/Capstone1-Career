def support_route(query, vector_store, generate):
    documents = vector_store.similarity_search(query)
    context = "\n".join(doc.page_content for doc in documents)
    answer = generate(context + query)
    return {"application output": answer}  # route endpoint uses the RAG answer
