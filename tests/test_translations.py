import json
from pathlib import Path

INTEGRATION_DIR = Path(__file__).parents[1] / "custom_components" / "ecoservice_waste_collection"
REQUIRED_STEPS = {
    "user": "municipality",
    "address": "address",
    "containers": "containers",
    "confirm": "vasa_enabled",
    "vasa": "vasa_username",
}
REQUIRED_ERRORS = {
    "cannot_connect",
    "invalid_municipality",
    "invalid_address",
    "container_not_found",
    "empty_schedule",
    "vasa_auth_failed",
}


def _key_paths(value, prefix=()):
    if not isinstance(value, dict):
        return set()
    paths = set()
    for key, child in value.items():
        path = (*prefix, key)
        paths.add(path)
        paths.update(_key_paths(child, path))
    return paths


def test_custom_integration_uses_translation_files_only():
    assert not (INTEGRATION_DIR / "strings.json").exists()


def test_english_and_lithuanian_translations_are_complete():
    loaded = {}
    for language in ("en", "lt"):
        translations = json.loads((INTEGRATION_DIR / "translations" / f"{language}.json").read_text(encoding="utf-8"))
        loaded[language] = translations
        config = translations["config"]

        for step, field in REQUIRED_STEPS.items():
            assert config["step"][step]["data"][field]

        assert REQUIRED_ERRORS <= config["error"].keys()

    assert _key_paths(loaded["en"]) == _key_paths(loaded["lt"])
