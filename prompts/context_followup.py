CONTEXT_FOLLOWUP_PROMPT = """

Determine whether the user's latest message

refers to the previously retrieved memory.



FOLLOW_UP:

The message clearly requests information

about the previous memory.



NEW_REQUEST:

The message introduces a separate request

or clearly refers to another subject.



UNCLEAR:

The reference cannot be established reliably.



Do not invent facts.

A new request for correction, deletion, or saving

must not be classified as a factual follow-up.





Important classification rules:



1. FOLLOW_UP includes questions about the previous

   memory, even when the requested detail is absent

   from that memory.



2. Missing information does not mean NEW_REQUEST.



3. Examples:

   Previous memory: Mom's apple pie recipe.



   "How many eggs?" -> FOLLOW_UP

   "How much butter?" -> FOLLOW_UP

   "What temperature?" -> FOLLOW_UP

   "How long should I bake it?" -> FOLLOW_UP



4. NEW_REQUEST applies when the user clearly

   introduces another subject, such as:

   "What about Grandma's banana recipe?"



5. Never invent missing information.



Broad memory discovery questions are NEW_REQUEST,

even when an active memory exists.



Examples:

"What recipe did I share earlier?" -> NEW_REQUEST

"What recipes do you remember?" -> NEW_REQUEST

"Which food preferences have I saved?" -> NEW_REQUEST



FOLLOW_UP should apply when the message clearly

continues discussing the previously selected memory.



Examples:

"How long should I bake it?" -> FOLLOW_UP

"What temperature?" -> FOLLOW_UP

"How much sugar?" -> FOLLOW_UP

"How many eggs?" -> FOLLOW_UP



A missing ingredient or field does not make

a contextual question a NEW_REQUEST.





"""
