from uuid import uuid4

from validators.event_validator import EventInput


def test_event_validator_normalizes_adjustment():
    event = EventInput(
        user_id="adh_correction_test",
        domain="cooking",
        event_type="meal_prepared",
        subject="dal",
        attributes={"adjustment": "reduced salt"},
        outcome="BETTER",
        source_utterance="I made dal with reduced salt.",
        request_id=uuid4(),
    )

    assert event.attributes["adjustment"] == "less_salt"
