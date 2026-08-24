from __future__ import annotations

import asyncio
import re
import unicodedata
from collections.abc import Iterable
from datetime import date
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import VASA_API_URL
from .models import CollectionRecord, PayableInvoice, normalize_date, normalize_dates


class VasaApiError(Exception):
    """VASA request failed without exposing credentials or private response data."""


class VasaAuthenticationError(VasaApiError):
    """VASA rejected the credentials or requires an unsupported login step."""


def _unwrap(payload: Any) -> Any:
    if isinstance(payload, dict):
        for key in ("result", "items"):
            if key in payload and payload[key] is not None:
                return _unwrap(payload[key])
    return payload


def _iter_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_dicts(child)


def _normalized_values(row: dict[str, Any]) -> dict[str, Any]:
    values = row.get("allColumnsValues") or row.get("columns") or row
    if isinstance(values, list):
        result = {}
        for item in values:
            if isinstance(item, dict):
                key = item.get("key") or item.get("name") or item.get("columnName") or item.get("title")
                if key:
                    result[str(key).casefold()] = item.get("value")
        return result
    if isinstance(values, dict):
        return {str(key).casefold(): value for key, value in values.items()}
    return {}


def _normalized_key(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value.casefold())
        if character.isalnum() and not unicodedata.combining(character)
    )


def _parse_amount(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r"[^0-9,.\-]", "", str(value))
    if not text:
        return None
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_payable_invoices(payload: Any) -> tuple[PayableInvoice, ...]:
    """Parse VASA's dynamic payable-invoices table."""
    invoices: set[PayableInvoice] = set()
    column_labels: dict[str, str] = {}
    for table in _iter_dicts(_unwrap(payload)):
        columns = table.get("columns")
        if not isinstance(columns, list):
            continue
        for column in columns:
            if not isinstance(column, dict):
                continue
            name = column.get("name")
            display_name = column.get("displayName")
            if name and display_name:
                column_labels[_normalized_key(str(name))] = _normalized_key(str(display_name))
    for row in _iter_dicts(_unwrap(payload)):
        values = _normalized_values(row)
        normalized = {_normalized_key(key): value for key, value in values.items()}
        normalized.update(
            {column_labels[key]: value for key, value in tuple(normalized.items()) if key in column_labels}
        )
        invoice_number = next(
            (
                value
                for key, value in normalized.items()
                if (("saskait" in key or "invoice" in key) and any(marker in key for marker in ("nr", "number", "no")))
            ),
            None,
        )
        raw_amount = next(
            (
                value
                for key, value in normalized.items()
                if ("moketin" in key or "payable" in key or "sumtopay" in key or "amounttopay" in key)
            ),
            None,
        )
        amount = _parse_amount(raw_amount)
        if invoice_number not in (None, "") and amount is not None:
            invoices.add(PayableInvoice(str(invoice_number).strip(), amount))
    return tuple(sorted(invoices, key=lambda item: item.invoice_number))


def parse_collection_records(payload: Any, inventory: str) -> tuple[CollectionRecord, ...]:
    """Parse either typed ABP DTOs or the generic selectable-table DTO."""
    records: set[CollectionRecord] = set()
    for row in _iter_dicts(_unwrap(payload)):
        values = _normalized_values(row)

        def find(*aliases: str, source: dict[str, Any] = values) -> Any:
            for key, value in source.items():
                if any(alias in key for alias in aliases):
                    return value
            return None

        parsed_date = normalize_date(find("data", "date", "serviceat"))
        servicing = find("aptarnav", "servic")
        if parsed_date is None or servicing is None:
            continue
        raw_weight = find("svoris", "weight")
        try:
            weight = float(str(raw_weight).replace(",", ".")) if raw_weight not in (None, "") else None
        except ValueError:
            weight = None
        records.add(
            CollectionRecord(
                date=parsed_date,
                inventory_number=inventory,
                servicing=str(servicing).strip(),
                reason=(str(find("priežast", "priezast", "reason")).strip() or None)
                if find("priežast", "priezast", "reason") is not None
                else None,
                weight_kg=weight,
            )
        )
    return tuple(sorted(records, key=lambda item: item.date, reverse=True))


def parse_calendar_dates(payload: Any) -> tuple[date, ...]:
    """Parse the dates highlighted in a VASA container calendar."""
    value = _unwrap(payload)
    if isinstance(value, dict):
        value = value.get("dates", [])
    return normalize_dates(value if isinstance(value, list) else [])


class VasaApi:
    def __init__(self, session: ClientSession, username: str, password: str, timeout: float = 30) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._timeout = ClientTimeout(total=timeout, connect=min(timeout, 10))
        self._token: str | None = None

    async def _json(self, method: str, path: str, _retry_auth: bool = True, **kwargs: Any) -> Any:
        headers = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            async with asyncio.timeout(self._timeout.total):
                async with self._session.request(
                    method, f"{VASA_API_URL}{path}", headers=headers, timeout=self._timeout, **kwargs
                ) as response:
                    if response.status in (401, 403):
                        if self._token and _retry_auth:
                            self._token = None
                            await self.authenticate()
                            return await self._json(method, path, _retry_auth=False, **kwargs)
                        raise VasaAuthenticationError("VASA authentication failed")
                    if response.status >= 400:
                        raise VasaApiError(f"VASA returned HTTP {response.status}")
                    return await response.json(content_type=None)
        except (TimeoutError, ClientError) as err:
            raise VasaApiError("Unable to reach VASA") from err

    async def authenticate(self) -> None:
        payload = await self._json(
            "POST",
            "/api/TokenAuth/Authenticate",
            json={
                "userNameOrEmailAddress": self._username,
                "password": self._password,
                "rememberClient": False,
            },
        )
        result = payload.get("result", payload) if isinstance(payload, dict) else {}
        token = result.get("accessToken") if isinstance(result, dict) else None
        if not token or result.get("requiresTwoFactorVerification"):
            raise VasaAuthenticationError("VASA credentials require verification or were rejected")
        self._token = str(token)

    async def histories_and_calendars(
        self, inventories: list[str]
    ) -> tuple[dict[str, tuple[CollectionRecord, ...]], dict[str, tuple[date, ...]]]:
        if not self._token:
            await self.authenticate()
        session = await self._json("GET", "/api/services/app/Session/GetCurrentLoginInformations")
        contracts = session.get("result", {}).get("availableContracts", [])
        collected: dict[str, list[CollectionRecord]] = {item: [] for item in inventories}
        calendars: dict[str, tuple[date, ...]] = {item: () for item in inventories}
        for contract in contracts:
            contract_id = contract.get("contractId") or contract.get("id")
            if contract_id is None:
                continue
            tolls = await self._json(
                "GET",
                "/api/services/app/TollObject/GetTollObjectsListByContractId",
                params={"ContractId": contract_id},
            )
            for toll in _iter_dicts(_unwrap(tolls)):
                toll_id = toll.get("tollObjectId") or toll.get("id")
                if toll_id is None:
                    continue
                table = await self._json(
                    "GET",
                    "/api/services/app/Orders/GetSelectableTable",
                    params={
                        "ContractId": contract_id,
                        "TollObjectId": toll_id,
                        "SkipCount": 0,
                        "MaxResultCount": 1000,
                    },
                )
                for row in _iter_dicts(_unwrap(table)):
                    values = _normalized_values(row)
                    inventory = next(
                        (
                            str(value).strip()
                            for key, value in values.items()
                            if "konteinerio nr" in key or "inventory" in key
                        ),
                        None,
                    )
                    if inventory not in collected:
                        continue
                    row_id = row.get("id") or row.get("Id") or values.get("id")
                    if row_id is None:
                        continue
                    calendar = await self._json(
                        "GET",
                        "/api/services/app/Orders/GetCalendarDates",
                        params={
                            "Id": row_id,
                            "ContractId": contract_id,
                            "TollObjectId": toll_id,
                        },
                    )
                    calendars[inventory] = parse_calendar_dates(calendar)
                    details = await self._json(
                        "GET",
                        "/api/services/app/Orders/GetSelectableRowObject",
                        params={
                            "Id": row_id,
                            "ContractId": contract_id,
                            "TollObjectId": toll_id,
                            "SkipCount": 0,
                            "MaxResultCount": 1000,
                        },
                    )
                    collected[inventory].extend(parse_collection_records(details, inventory))
        histories = {
            inventory: tuple(sorted(set(records), key=lambda item: item.date, reverse=True))
            for inventory, records in collected.items()
        }
        return histories, calendars

    async def histories(self, inventories: list[str]) -> dict[str, tuple[CollectionRecord, ...]]:
        histories, _ = await self.histories_and_calendars(inventories)
        return histories

    async def payable_invoices(self) -> tuple[PayableInvoice, ...]:
        if not self._token:
            await self.authenticate()
        payload = await self._json(
            "GET",
            "/api/services/app/InvoiceAndPayment/GetPayableInvoicesList",
        )
        return parse_payable_invoices(payload)
