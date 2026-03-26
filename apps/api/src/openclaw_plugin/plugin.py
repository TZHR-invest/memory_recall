from typing import Dict, Any, Optional

from src.services.lossless.memory_recall_engine import (
    MemoryRecallEngine,
    memory_recall_engine,
)


def create_memory_recall_engine(config: Optional[Dict[str, Any]] = None):
    return MemoryRecallEngine(config=config)


def get_engine_info() -> Dict[str, Any]:
    return {
        "id": "memory-recall",
        "name": "Memory Recall Engine",
        "version": "3.0.0",
        "owns_compaction": True,
        "capabilities": [
            "ingest",
            "assemble",
            "compact",
            "recall",
            "expand",
        ],
    }


__all__ = [
    "create_memory_recall_engine",
    "get_engine_info",
    "MemoryRecallEngine",
]
