def answer(query, vector_store, generate):
    documents = vector_store.similarity_search(query)
    context = "\n".join(doc.page_content for doc in documents)
    return generate(context + query)
