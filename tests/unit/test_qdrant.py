# tests/unit/test_qdrant.py
import pytest
import asyncio
import httpx


def test_filter_low_scores(monkeypatch):
    """Test that Qdrant search filters out low-score results"""
    
    async def fake_search(*args, **kwargs):
        # Mock qdrant_client.models.ScoredPoint objects
        class MockPoint:
            def __init__(self, id, score, payload):
                self.id = id
                self.score = score
                self.payload = payload
        
        return [
            MockPoint(id=1, score=0.2, payload={"signature": "low", "fix_steps": "a", "project": "x", "created_at": "t1"}),
            MockPoint(id=2, score=0.95, payload={"signature": "high", "fix_steps": "b", "project": "y", "created_at": "t2"})
        ]

    # Mock the managed_qdrant_client context manager
    class MockClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def search(self, *args, **kwargs):
            return await fake_search(*args, **kwargs)
    
    monkeypatch.setattr("agent.utils.managed_qdrant_client", lambda url: MockClient())
    # Also mock SentenceTransformer to avoid loading the model
    class MockModel:
        def encode(self, query, normalize_embeddings=True):
            return [0.1] * 10  # dummy vector
    monkeypatch.setattr("sentence_transformers.SentenceTransformer", lambda name, cache_folder=None: MockModel())
    
    from agent.tools import qdrant_search
    
    res = asyncio.run(qdrant_search("test", score_threshold=0.5))
    
    # Only the high-score result should be returned
    assert len(res) == 1
    assert res[0]["score"] == 0.95


def test_empty_results_when_all_below_threshold(monkeypatch):
    """Test that empty list is returned when all scores are below threshold"""
    
    async def fake_search(*args, **kwargs):
        class MockPoint:
            def __init__(self, id, score, payload):
                self.id = id
                self.score = score
                self.payload = payload
        
        return [
            MockPoint(id=1, score=0.2, payload={"signature": "low1", "fix_steps": "a", "project": "x", "created_at": "t1"}),
            MockPoint(id=2, score=0.3, payload={"signature": "low2", "fix_steps": "b", "project": "y", "created_at": "t2"})
        ]

    class MockClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def search(self, *args, **kwargs):
            return await fake_search(*args, **kwargs)
    
    monkeypatch.setattr("agent.utils.managed_qdrant_client", lambda url: MockClient())
    class MockModel:
        def encode(self, query, normalize_embeddings=True):
            return [0.1] * 10
    monkeypatch.setattr("sentence_transformers.SentenceTransformer", lambda name, cache_folder=None: MockModel())
    
    from agent.tools import qdrant_search
    
    res = asyncio.run(qdrant_search("test", score_threshold=0.5))
    
    # All results are below threshold, should return empty list
    assert len(res) == 0
    assert res == []


def test_null_score_filtered(monkeypatch):
    """Test that results with null scores are filtered out"""
    
    async def fake_search(*args, **kwargs):
        class MockPoint:
            def __init__(self, id, score, payload):
                self.id = id
                self.score = score
                self.payload = payload
        
        return [
            MockPoint(id=1, score=None, payload={"signature": "null", "fix_steps": "a", "project": "x", "created_at": "t1"}),
            MockPoint(id=2, score=0.95, payload={"signature": "high", "fix_steps": "b", "project": "y", "created_at": "t2"})
        ]

    class MockClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def search(self, *args, **kwargs):
            return await fake_search(*args, **kwargs)
    
    monkeypatch.setattr("agent.utils.managed_qdrant_client", lambda url: MockClient())
    class MockModel:
        def encode(self, query, normalize_embeddings=True):
            return [0.1] * 10
    monkeypatch.setattr("sentence_transformers.SentenceTransformer", lambda name, cache_folder=None: MockModel())
    
    from agent.tools import qdrant_search
    
    res = asyncio.run(qdrant_search("test", score_threshold=0.5))
    
    # Only the valid high-score result should be returned
    assert len(res) == 1
    assert res[0]["score"] == 0.95
