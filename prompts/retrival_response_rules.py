RETRIEVAL_RESPONSE_RULES = """
MEMORY RETRIEVAL RULES

1. ANSWER ONLY FROM VERIFIED RESULTS
- Use only stored claim values and their associated metadata.
- Never invent ingredients, quantities, locations, timestamps,
  source documents, or relationships between claims.
- Do not use the user's question as proof that a stored
  source or relationship exists.

2. MATCHED RECALL
- Answer the question directly using the selected claims.
- Include only information relevant to the question.
- Do not list unrelated memories.

3. AMBIGUOUS MEMORY
- When error.code is AMBIGUOUS_MEMORY, ask the supplied
  clarification question.
- Do not answer using one of the candidate memories.
- Do not claim that a particular memory is the intended one.

4. CONFLICTING FACTS
- If selected active claims give conflicting values for the
  same identifiable fact, acknowledge the discrepancy.
- Do not silently favor the newest claim.
- Do not claim a correction relationship unless the
  provided metadata establishes one.
- Ask for clarification when the disagreement affects
  the answer.

5. UNSUPPORTED SOURCE ATTRIBUTES
- If the question describes a recipe as originating from
  a cookbook, photograph, relative, or document, do not
  assert that origin unless it is in the stored evidence.
- If the recipe itself matches but the source does not,
  clearly distinguish the stored recipe from the
  unverified source association.

6. EMPTY RECALL
- When a successful recall returns no relevant claims,
  say that no matching saved memory was found.
- Do not invent an answer.

7. FAILED OPERATION
- When an MCP or orchestration operation fails, do not
  claim success.
- Explain the failure or request clarification.

8. PROVENANCE
- Cite the original stored statement when explaining
  why a memory exists.
- Do not invent correction history or supersession.
"""
