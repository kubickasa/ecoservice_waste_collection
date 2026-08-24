import asyncio
from datetime import date

from custom_components.ecoservice_waste_collection.models import (
    CollectionRecord,
    latest_collection_record,
    latest_serviced_record,
    yearly_serviced_weight,
)
from custom_components.ecoservice_waste_collection.vasa_api import (
    VasaApi,
    parse_calendar_dates,
    parse_collection_records,
    parse_payable_invoices,
)


class _Response:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def json(self, content_type=None):
        return self._payload


class _Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.authorization_headers = []

    def request(self, method, url, headers, **kwargs):
        self.authorization_headers.append(headers.get("Authorization"))
        return next(self.responses)


def test_parse_anonymized_vasa_history():
    payload = {
        "result": {
            "items": [
                {
                    "allColumnsValues": {
                        "Data": "2026-08-08",
                        "Aptarnavimas": "Aptarnautas",
                        "Priežastis": "",
                        "Svoris, kg.": "46",
                    }
                },
                {
                    "allColumnsValues": {
                        "Data": "2026-07-25",
                        "Aptarnavimas": "Neaptarnautas",
                        "Priežastis": "Neišstumtas konteineris",
                        "Svoris, kg.": 0,
                    }
                },
            ]
        }
    }
    records = parse_collection_records(payload, "00-L-000000")
    assert records[0].date == date(2026, 8, 8)
    assert records[0].weight_kg == 46
    assert records[1].reason == "Neišstumtas konteineris"


def test_parse_vasa_container_calendar_dates():
    payload = {"result": {"dates": ["2026-09-05T00:00:00", "2026-09-19T00:00:00", "2026-10-03T00:00:00"]}}

    assert parse_calendar_dates(payload) == (
        date(2026, 9, 5),
        date(2026, 9, 19),
        date(2026, 10, 3),
    )


def test_vasa_calendar_is_requested_for_the_matching_container_row():
    requested = []

    class StubApi(VasaApi):
        async def _json(self, method, path, **kwargs):
            requested.append((path, kwargs.get("params")))
            if path.endswith("GetCurrentLoginInformations"):
                return {"result": {"availableContracts": [{"contractId": 10}]}}
            if path.endswith("GetTollObjectsListByContractId"):
                return {"result": [{"id": 20}]}
            if path.endswith("GetSelectableTable"):
                return {
                    "result": [
                        {
                            "id": 30,
                            "allColumnsValues": {"Konteinerio Nr.": "13-P-103319"},
                        }
                    ]
                }
            if path.endswith("GetCalendarDates"):
                return {"result": {"dates": ["2026-09-05", "2026-09-19"]}}
            if path.endswith("GetSelectableRowObject"):
                return {"result": {"items": []}}
            raise AssertionError(path)

    api = StubApi(None, "user", "password")
    api._token = "token"

    _, calendars = asyncio.run(api.histories_and_calendars(["13-P-103319"]))

    assert calendars["13-P-103319"] == (date(2026, 9, 5), date(2026, 9, 19))
    assert (
        "/api/services/app/Orders/GetCalendarDates",
        {"Id": 30, "ContractId": 10, "TollObjectId": 20},
    ) in requested


def test_yearly_weight_counts_only_successful_services():
    records = (
        CollectionRecord(date(2026, 1, 2), "00-P-000001", "Aptarnautas", None, 12.5),
        CollectionRecord(date(2026, 2, 2), "00-P-000001", "Neaptarnautas", "Kliūtis", 4),
        CollectionRecord(date(2025, 12, 30), "00-P-000001", "Aptarnautas", None, 10),
        CollectionRecord(date(2026, 3, 2), "00-P-000001", "Aptarnautas", None, None),
    )
    assert yearly_serviced_weight(records, 2026) == 12.5
    assert latest_serviced_record(records) == records[3]
    assert latest_collection_record(records) == records[3]


def test_latest_collection_record_includes_unsuccessful_attempt():
    records = (
        CollectionRecord(date(2026, 8, 8), "00-P-000001", "Aptarnautas", None, 6),
        CollectionRecord(date(2026, 8, 22), "00-P-000001", "Neaptarnautas", "Neišstumtas konteineris", 0),
    )

    assert latest_serviced_record(records) == records[0]
    assert latest_collection_record(records) == records[1]


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
            ],
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

    assert requested == [("GET", "/api/services/app/InvoiceAndPayment/GetPayableInvoicesList")]
    assert invoices[0].amount == 50.08


def test_expired_vasa_token_is_refreshed_and_request_retried_once():
    session = _Session(
        [
            _Response(401, {}),
            _Response(200, {"result": {"accessToken": "new-token"}}),
            _Response(200, {"result": {"ok": True}}),
        ]
    )
    api = VasaApi(session, "user", "password")
    api._token = "expired-token"

    payload = asyncio.run(api._json("GET", "/api/services/app/Test"))

    assert payload == {"result": {"ok": True}}
    assert api._token == "new-token"
    assert session.authorization_headers == ["Bearer expired-token", None, "Bearer new-token"]
