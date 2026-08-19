from custom_components.ecoservice_waste_collection.api import (
    EcoserviceApi,
    natural_sort_key,
    normalize_search_text,
    powerbi_string_literal,
)


def test_headers_do_not_contain_private_values():
    headers = EcoserviceApi._headers("public-key")
    assert headers["X-PowerBI-ResourceKey"] == "public-key"
    assert "ActivityId" in headers and "RequestId" in headers


def test_powerbi_string_literal():
    assert powerbi_string_literal("Vilniaus m.") == "'Vilniaus m.'"
    assert powerbi_string_literal("O'Connor") == "'O''Connor'"


def test_search_normalization_is_case_and_accent_insensitive():
    assert normalize_search_text("  ĄŽUOLŲ  ") == "azuolu"
    assert normalize_search_text("Rukainių g.").startswith(
        normalize_search_text("RU")
    )


def test_natural_address_sorting():
    addresses = ["B gatvė", "Aitvarų g. 16", "Ąžuolų g. 1", "Aitvarų g. 4"]

    assert sorted(addresses, key=natural_sort_key) == [
        "Aitvarų g. 4",
        "Aitvarų g. 16",
        "Ąžuolų g. 1",
        "B gatvė",
    ]
