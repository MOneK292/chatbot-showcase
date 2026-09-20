import pytest
import numpy as np

def cosine_similarity_search(chunks_data, query_embedding, top_k=5):
    if not chunks_data:
        return []
        
    vectors = [c["embedding"] for c in chunks_data]
    vectors_np = np.array(vectors)
    query_np = np.array(query_embedding)
    
    vectors_norm = np.linalg.norm(vectors_np, axis=1, keepdims=True)
    query_norm = np.linalg.norm(query_np)
    
    vectors_norm[vectors_norm == 0] = 1.0
    if query_norm == 0:
        query_norm = 1.0
        
    normalized_vectors = vectors_np / vectors_norm
    normalized_query = query_np / query_norm
    
    similarities = np.dot(normalized_vectors, normalized_query)
    top_indices = np.argsort(similarities)[-top_k:][::-1]
    
    results = []
    for idx in top_indices:
        res = dict(chunks_data[idx])
        res["score"] = float(similarities[idx])
        results.append(res)
        
    return results

def test_numpy_cosine_similarity():
    chunks = [
        {"chunk_id": 1, "text": "Apples and oranges are fruits", "embedding": [0.9, 0.1, 0.0, 0.0]},
        {"chunk_id": 2, "text": "Cars and trucks are vehicles", "embedding": [0.0, 0.0, 0.9, 0.1]}
    ]
    
    query = [0.8, 0.2, 0.0, 0.0]
    
    results = cosine_similarity_search(chunks, query, top_k=2)
    
    assert len(results) == 2
    assert results[0]["chunk_id"] == 1
    assert results[0]["score"] > results[1]["score"]

