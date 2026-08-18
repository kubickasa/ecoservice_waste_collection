from datetime import date

from custom_components.ecoservice_waste_collection.models import CollectionRecord, yearly_serviced_weight
from custom_components.ecoservice_waste_collection.vasa_api import parse_collection_records


def test_parse_anonymized_vasa_history():
    payload = {"result": {"items": [
        {"allColumnsValues": {"Data": "2026-08-08", "Aptarnavimas": "Aptarnautas", "Priežastis": "", "Svoris, kg.": "46"}},
        {"allColumnsValues": {"Data": "2026-07-25", "Aptarnavimas": "Neaptarnautas", "Priežastis": "Neišstumtas konteineris", "Svoris, kg.": 0}},
    ]}}
    records = parse_collection_records(payload, "00-L-000000")
    assert records[0].date == date(2026, 8, 8)
    assert records[0].weight_kg == 46
    assert records[1].reason == "Neišstumtas konteineris"


def test_yearly_weight_counts_only_successful_services():
    records = (
        CollectionRecord(date(2026, 1, 2), "00-P-000001", "Aptarnautas", None, 12.5),
        CollectionRecord(date(2026, 2, 2), "00-P-000001", "Neaptarnautas", "Kliūtis", 4),
        CollectionRecord(date(2025, 12, 30), "00-P-000001", "Aptarnautas", None, 10),
        CollectionRecord(date(2026, 3, 2), "00-P-000001", "Aptarnautas", None, None),
    )
    assert yearly_serviced_weight(records, 2026) == 12.5
