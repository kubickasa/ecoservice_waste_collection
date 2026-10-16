from datetime import date

from custom_components.ecoservice_waste_collection.models import (
    CollectionRecord,
    Container,
    Schedule,
    WasteType,
    days_until,
    history_waste_types,
    next_collection,
    next_collection_for_waste,
    normalize_date,
    normalize_dates,
    schedules_have_upcoming_collections,
    selected_waste_types,
    waste_type_from_inventory,
)


def test_waste_type_inventory_formats():
    assert waste_type_from_inventory("12-L-0001") is WasteType.MIXED
    assert waste_type_from_inventory("p123") is WasteType.PAPER
    assert waste_type_from_inventory(" 99_s_42") is WasteType.GLASS
    assert waste_type_from_inventory("13-Z-000001") is WasteType.GREEN
    assert waste_type_from_inventory("94-X-300544") is WasteType.UNKNOWN
    assert waste_type_from_inventory("12345") is WasteType.UNKNOWN


def test_normalize_dates_and_dedupe():
    assert normalize_date("19/08/2026") == date(2026, 8, 19)
    assert normalize_date("2026-08-19T00:00:00") == date(2026, 8, 19)
    assert normalize_date(1787356800000) == date(2026, 8, 22)
    assert normalize_date("") is None
    assert normalize_date("bad") is None
    assert normalize_dates(["19/08/2026", "2026-08-19", None, "20.08.2026"]) == (date(2026, 8, 19), date(2026, 8, 20))


def test_next_and_days_until():
    dates = (date(2026, 8, 17), date(2026, 8, 19), date(2026, 8, 22))
    today = date(2026, 8, 18)
    assert next_collection(dates, today) == date(2026, 8, 19)
    assert days_until(dates, today) == 1
    assert days_until((), today) is None


def test_next_collection_for_each_waste_type():
    schedules = (
        Schedule(
            Container("P-1", WasteType.PAPER),
            (date(2026, 8, 20), date(2026, 9, 1)),
        ),
        Schedule(
            Container("P-2", WasteType.PAPER),
            (date(2026, 8, 19),),
        ),
        Schedule(Container("S-1", WasteType.GLASS), (date(2026, 8, 25),)),
    )

    assert next_collection_for_waste(schedules, WasteType.PAPER, date(2026, 8, 19)) == (date(2026, 8, 19), "P-2")
    assert next_collection_for_waste(schedules, WasteType.MIXED, date(2026, 8, 19)) is None


def test_all_selected_containers_need_an_upcoming_date_for_complete_data():
    schedules = {
        "P-1": Schedule(Container("P-1", WasteType.PAPER), (date(2026, 8, 20),)),
        "S-1": Schedule(Container("S-1", WasteType.GLASS), (date(2026, 8, 18),)),
    }

    assert schedules_have_upcoming_collections(schedules, ["P-1"], date(2026, 8, 19))
    assert not schedules_have_upcoming_collections(schedules, ["P-1", "S-1"], date(2026, 8, 19))
    assert not schedules_have_upcoming_collections(schedules, ["P-1", "L-1"], date(2026, 8, 19))


def test_waste_sensor_types_follow_selected_containers():
    assert selected_waste_types(["12-L-0001", "13-Z-000001"]) == {WasteType.MIXED, WasteType.GREEN}
    assert selected_waste_types([]) == set()


def test_history_sensor_types_need_vasa_source_or_history():
    vasa = "https://savitarna.vasa.lt/orders"
    sources = {"12-L-0001": vasa, "13-Z-000001": "https://ecoservice.lt/grafikai/", "14-P-0002": "other"}
    histories = {"14-P-0002": (CollectionRecord(date(2026, 8, 1), "14-P-0002", "Aptarnautas", None, 10.0),)}
    inventories = ["12-L-0001", "13-Z-000001", "14-P-0002"]

    assert history_waste_types(inventories, sources, histories, vasa) == {WasteType.MIXED, WasteType.PAPER}
    assert history_waste_types(["13-Z-000001"], sources, {"13-Z-000001": ()}, vasa) == set()
