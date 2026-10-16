import importlib
import sys
from types import ModuleType
from unittest.mock import patch

import pytest


@pytest.fixture(scope="module")
def orchestrator():
    # Isolate import-time configuration without opening database or API connections.
    database = ModuleType("database")
    database.SessionLocal = None
    with (
        patch.dict(sys.modules, {"database": database}),
        patch("dotenv.load_dotenv"),
        patch("openai.OpenAI"),
        patch("logging.basicConfig"),
    ):
        yield importlib.import_module("client.orchestrator")
