from custom_components.ecoservice_waste_collection.api import EcoserviceApi, powerbi_string_literal


def test_headers_do_not_contain_private_values():
    headers = EcoserviceApi._headers("public-key")
    assert headers["X-PowerBI-ResourceKey"] == "public-key"
    assert "ActivityId" in headers and "RequestId" in headers


def test_powerbi_string_literal():
    assert powerbi_string_literal("Vilniaus m.") == "'Vilniaus m.'"
    assert powerbi_string_literal("O'Connor") == "'O''Connor'"
