CONVERSATION_DECISION_PROMPT = """
Interpret the latest user message relative to ONE previously retrieved memory.
The backend verified that this memory is currently ACTIVE for this user.
You interpret intent only; you do not select keys or execute tools.

Return the schema fields:
- target: PREVIOUS_MEMORY, NEW_REQUEST, or AMBIGUOUS
- operation: RECALL, CORRECT_MEMORY, FORGET, EXPLAIN, or NONE
- replacement_value: full standalone updated fact, or null
- clarification_question: question if AMBIGUOUS, otherwise null

Rules:
1. Pronouns 'that', 'it', 'this' and implicit follow-up questions normally
   refer to the previous memory, unless the user names a different topic.
   A pronoun by itself is not a reason for AMBIGUOUS.
2. PREVIOUS_MEMORY / RECALL: requests details about the previous memory.
   Return this even if the requested detail is not included in that memory.
3. PREVIOUS_MEMORY / CORRECT_MEMORY: changes the previous memory.
   For unambiguous edits, return a complete standalone replacement value
   preserving all unaffected facts. If the edit is incomplete or a qualified
   change cannot be safely expressed, replacement_value must be null.
4. PREVIOUS_MEMORY / FORGET: removes the previous memory.
5. PREVIOUS_MEMORY / EXPLAIN: asks about the source of the previous memory.
6. NEW_REQUEST / NONE: explicitly different subject or broad memory search.
   Independent broad questions like "What do I enjoy?" or "What do I like?"
   are NEW_REQUEST even when a previous memory exists. Never answer these
   solely from the last reference.
7. AMBIGUOUS / NONE: genuinely unclear referent; ask a clarifying question.
8. Never invent details, infer an unstated replacement, or select a memory key.
9. For target!=PREVIOUS_MEMORY, operation=NONE and replacement_value=null.
   For operation!=CORRECT_MEMORY, replacement_value=null.

Examples for previous_memory='I prefer aisle seats on flights':
'Change that to window' => PREVIOUS_MEMORY, CORRECT_MEMORY,
  replacement_value='I prefer window seats on flights.'
'Change that' => PREVIOUS_MEMORY, CORRECT_MEMORY, replacement_value=null
'Forget that' => PREVIOUS_MEMORY, FORGET, replacement_value=null
'Why do you remember that?' => PREVIOUS_MEMORY, EXPLAIN, replacement_value=null
'What is my seat preference?' => PREVIOUS_MEMORY, RECALL, replacement_value=null
'What hiking preferences do I have?' => NEW_REQUEST, NONE, replacement_value=null

Examples for previous_memory='Bake Mom’s apple pie at 350 F for 40 minutes':
'How long should I bake it?' => PREVIOUS_MEMORY, RECALL, replacement_value=null
'What about Grandma’s banana recipe?' => NEW_REQUEST, NONE, replacement_value=null
"""
