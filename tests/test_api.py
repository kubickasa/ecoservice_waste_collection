from custom_components.ecoservice_waste_collection.api import EcoserviceApi


def test_headers_do_not_contain_private_values():
    headers = EcoserviceApi._headers("public-key")
    assert headers["X-PowerBI-ResourceKey"] == "public-key"
    assert "ActivityId" in headers and "RequestId" in headers

