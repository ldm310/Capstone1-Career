def test_answer(vector_store, generate):
    documents = vector_store.similarity_search("q")
    context = "\n".join(doc.page_content for doc in documents)
    assert generate(context)
