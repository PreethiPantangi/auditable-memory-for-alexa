RESOLVE_PENDING_CORRECTION_PROMPT = """

A user was asked whether to forget an

existing memory or replace it.



Classify the latest user message.



REPLACE:

The user clearly provides a complete new

replacement value for the targeted memory.

Extract the standalone replacement fact.



FORGET:

The user explicitly chooses to forget/remove

the targeted saved memory.



CANCEL:

The user explicitly cancels the operation.



NEW_REQUEST:

The user clearly starts an unrelated request.



UNCLEAR:

The message is ambiguous, incomplete, or

only chooses "replace" without giving a

replacement value.



Examples:

Old: "chocolate brownie with hot fudge"



"I now eat chocolate brownie without hot fudge"

-> REPLACE

replacement_value:

"eats chocolate brownie without hot fudge"



"Replace it"

-> UNCLEAR



"Forget that preference"

-> FORGET



"Never mind"

-> CANCEL



"What's my hiking preference?"

-> NEW_REQUEST



Do not infer a replacement from the old claim.

Do not store instructions, questions, or a

bare yes/no as replacement values.



For statuses other than REPLACE,

replacement_value must be null.

"""
