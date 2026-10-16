RESOLVE_CORRECTION_TARGET_PROMPT = """

Identify the EXISTING memory targeted by

the user's correction request.



MATCHED:

Exactly one active memory clearly matches.



AMBIGUOUS:

Multiple active memories might match.



NOT_FOUND:

No existing memory can be identified reliably.



The user may say a preference is no longer true

without providing a replacement.



Example:

Old memory: "chocolate brownie with hot fudge"

User: "I no longer eat chocolate brownie

with hot fudge."

Result: MATCHED with that old memory's key.



Do not select a memory merely because it

belongs to the same category.



Return only a memory_key supplied in candidates.

Do not invent keys.

"""
