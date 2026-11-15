from types import SimpleNamespace

from custom_components.ecoservice_waste_collection.entity import EcoserviceEntity


def test_entity_remains_available_with_cached_data_after_refresh_failure():
    entity = object.__new__(EcoserviceEntity)
    entity.coordinator = SimpleNamespace(data={"13-L-1": object()}, last_update_success=False)

    assert entity.available is True


def test_entity_is_unavailable_before_any_data_has_loaded():
    entity = object.__new__(EcoserviceEntity)
    entity.coordinator = SimpleNamespace(data=None, last_update_success=False)

    assert entity.available is False
