import re

COOKING_ADJUSTMENTS = {
    "less_salt": {
        "less salt",
        "reduced salt",
        "decreased salt",
        "lower salt",
        "less sodium",
        "reduced sodium",
        "cut down salt",
    },
    "more_salt": {
        "more salt",
        "extra salt",
        "increased salt",
        "added more salt",
    },
    "less_sugar": {
        "less sugar",
        "reduced sugar",
        "decreased sugar",
        "lower sugar",
    },
    "more_sugar": {
        "more sugar",
        "extra sugar",
        "increased sugar",
    },
    "less_spice": {
        "less spice",
        "less spicy",
        "reduced spice",
        "milder",
    },
    "more_spice": {
        "more spice",
        "extra spice",
        "spicier",
        "increased spice",
    },
}


NORMALIZATION_LOOKUP = {
    phrase: canonical
    for canonical, phrases in COOKING_ADJUSTMENTS.items()
    for phrase in phrases | {canonical}
}


def normalize_adjustment(value: str) -> str:
    normalized = re.sub(
        r"\s+",
        " ",
        value.strip().lower().replace("_", " "),
    )

    return NORMALIZATION_LOOKUP.get(
        normalized,
        normalized.replace(" ", "_"),
    )
