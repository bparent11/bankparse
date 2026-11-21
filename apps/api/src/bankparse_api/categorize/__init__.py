"""Categorization of operations: merchant memory + user rules + a local LLM (Ollama).

Priority of sources (``transaction.category_source``):
1. ``user``   - category chosen by hand for this very operation, never overwritten;
2. ``rule``   - the user's rule for the merchant (also used as an example in the LLM prompt);
3. ``memory`` - the merchant was already classified by the LLM, reused without a new call;
4. ``llm``    - classified by the LLM during this run.

Nothing leaves the machine: the only model called is the local Ollama server.
"""
