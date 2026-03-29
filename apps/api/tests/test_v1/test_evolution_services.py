import pytest
from pathlib import Path
import sys
import os

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

from src.services.evolution.temporal_service import temporal_service, TemporalInfo
from src.services.evolution.chunking_service import chunking_service, Chunk
from datetime import datetime, timedelta


def test_calculate_expiration():
    """Test expiration calculation"""
    created = datetime.utcnow()

    exp_temp = temporal_service.calculate_expiration("temporary", created)
    assert (exp_temp - created).days == 1

    exp_short = temporal_service.calculate_expiration("short_term", created)
    assert (exp_short - created).days == 30

    exp_long = temporal_service.calculate_expiration("long_term", created)
    assert (exp_long - created).days == 365


def test_get_temporal_info():
    """Test temporal info extraction"""
    memory = {
        "event_date": datetime.utcnow(),
        "expiration_date": datetime.utcnow() + timedelta(days=30),
        "memory_lifespan": "short_term",
    }

    info = temporal_service.get_temporal_info(memory)

    assert info.memory_lifespan == "short_term"
    assert info.days_remaining is not None
    assert info.days_remaining <= 30


def test_chunk_sentence():
    """Test sentence chunking"""
    content = "这是第一句话。这是第二句话。这是第三句话。这是第四句话。"

    chunks = chunking_service.chunk(content, strategy="sentence")

    assert len(chunks) >= 1
    assert all(isinstance(c, Chunk) for c in chunks)


def test_chunk_semantic():
    """Test semantic chunking"""
    content = "段落一内容。\n\n段落二内容。\n\n段落三内容。"

    chunks = chunking_service.chunk(content, strategy="semantic")

    assert len(chunks) >= 1


def test_chunk_fixed():
    """Test fixed chunking"""
    content = "A" * 1000

    chunks = chunking_service.chunk(content, strategy="fixed")

    assert len(chunks) >= 1
