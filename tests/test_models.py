from datetime import date

from custom_components.ecoservice_waste_collection.models import (
    WasteType,
    days_until,
    next_collection,
    normalize_date,
    normalize_dates,
    waste_type_from_inventory,
)


def test_waste_type_inventory_formats():
    assert waste_type_from_inventory("12-L-0001") is WasteType.MIXED
    assert waste_type_from_inventory("p123") is WasteType.PAPER
    assert waste_type_from_inventory(" 99_s_42") is WasteType.GLASS
    assert waste_type_from_inventory("94-Z-300544") is WasteType.UNKNOWN
    assert waste_type_from_inventory("12345") is WasteType.UNKNOWN


def test_normalize_dates_and_dedupe():
    assert normalize_date("19/08/2026") == date(2026, 8, 19)
    assert normalize_date("2026-08-19T00:00:00") == date(2026, 8, 19)
    assert normalize_date(1787356800000) == date(2026, 8, 22)
    assert normalize_date("") is None
    assert normalize_date("bad") is None
    assert normalize_dates(["19/08/2026", "2026-08-19", None, "20.08.2026"]) == (date(2026,8,19), date(2026,8,20))


def test_next_and_days_until():
    dates = (date(2026,8,17), date(2026,8,19), date(2026,8,22))
    today = date(2026,8,18)
    assert next_collection(dates, today) == date(2026,8,19)
    assert days_until(dates, today) == 1
    assert days_until((), today) is None
