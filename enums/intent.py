from enum import StrEnum


class MemoryIntent(StrEnum):
    REMEMBER = "remember"
    RECALL = "recall"
    CORRECT_MEMORY = "correct_memory"
    FORGET = "forget"
    EXPLAIN = "explain"
    MEMORY_HISTORY = "memory_history"
