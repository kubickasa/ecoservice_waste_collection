import json
from pathlib import Path

INTEGRATION_DIR = (
    Path(__file__).parents[1] / "custom_components" / "ecoservice_waste_collection"
)
REQUIRED_STEPS = {
    "user": "municipality",
    "address_search": "address_search",
    "address": "address",
    "containers": "containers",
    "confirm": "vasa_enabled",
    "vasa": "vasa_username",
}
REQUIRED_ERRORS = {
    "cannot_connect",
    "invalid_municipality",
    "address_not_found",
    "invalid_address",
    "container_not_found",
    "empty_schedule",
    "vasa_auth_failed",
}


def test_custom_integration_uses_translation_files_only():
    assert not (INTEGRATION_DIR / "strings.json").exists()


def test_english_and_lithuanian_translations_are_complete():
    for language in ("en", "lt"):
        translations = json.loads(
            (INTEGRATION_DIR / "translations" / f"{language}.json").read_text(
                encoding="utf-8"
            )
        )
        config = translations["config"]

        for step, field in REQUIRED_STEPS.items():
            assert config["step"][step]["data"][field]

        assert REQUIRED_ERRORS <= config["error"].keys()
