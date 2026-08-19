import asyncio
from datetime import date

from custom_components.ecoservice_waste_collection.models import (
    CollectionRecord,
    latest_serviced_record,
    yearly_serviced_weight,
)
from custom_components.ecoservice_waste_collection.vasa_api import (
    VasaApi,
    parse_collection_records,
    parse_payable_invoices,
)


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
    assert latest_serviced_record(records) == records[3]


def test_parse_vasa_payable_invoices_and_total():
    payload = {
        "result": {
            "columns": [
                {"name": "InvoiceCode", "displayName": "Sąskaitos nr."},
                {"name": "Debt", "displayName": "Mokėtina suma"},
            ],
            "rows": [
                {
                    "allColumnsValues": {
                        "Sąskaitos nr.": "MP27527263",
                        "Mokėtina suma": "50,08 €",
                    }
                },
                {
                    "allColumnsValues": {
                        "InvoiceCode": "MP27527264",
                        "Debt": 12.5,
                    }
                },
            ]
        }
    }

    invoices = parse_payable_invoices(payload)

    assert [(item.invoice_number, item.amount) for item in invoices] == [
        ("MP27527263", 50.08),
        ("MP27527264", 12.5),
    ]
    assert round(sum(item.amount for item in invoices), 2) == 62.58


def test_payable_invoices_uses_vasa_billing_endpoint():
    requested = []

    class StubApi(VasaApi):
        async def _json(self, method, path, **kwargs):
            requested.append((method, path))
            return {
                "result": {
                    "rows": [
                        {
                            "allColumnsValues": {
                                "InvoiceNumber": "MP27527263",
                                "AmountToPay": "50,08",
                            }
                        }
                    ]
                }
            }

    api = StubApi(None, "user", "password")
    api._token = "token"

    invoices = asyncio.run(api.payable_invoices())

    assert requested == [
        ("GET", "/api/services/app/InvoiceAndPayment/GetPayableInvoicesList")
    ]
    assert invoices[0].amount == 50.08
