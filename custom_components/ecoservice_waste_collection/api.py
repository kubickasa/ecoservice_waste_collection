from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import REPORT_URL
from .models import Container, Schedule, normalize_dates, waste_type_from_inventory

ADDRESS_QUERY_LIMIT = 30_000


class EcoserviceApiError(Exception):
    """Public report could not be queried."""


class EcoserviceNotFound(EcoserviceApiError):
    """Requested source value does not exist."""


def powerbi_string_literal(value: str) -> str:
    """Encode text using the Power BI semantic-query literal format."""
    return f"'{value.replace(chr(39), chr(39) * 2)}'"


def normalize_search_text(value: str) -> str:
    """Normalize text for case- and accent-insensitive prefix matching."""
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value.casefold().strip())
        if not unicodedata.combining(character)
    )


def natural_sort_key(value: str) -> tuple[tuple[int, str | int], ...]:
    """Return an accent-insensitive key that sorts embedded numbers naturally."""
    return tuple(
        (1, int(part)) if part.isdigit() else (0, part)
        for part in re.split(r"(\d+)", normalize_search_text(value))
        if part
    )


@dataclass(slots=True)
class _Metadata:
    cluster: str
    resource_key: str
    dataset_id: str
    entity: str
    municipality: str
    address: str
    inventory: str
    collection_date: str
    capacity: str | None
    schedule_entity: str
    schedule_municipality: str
    schedule_address: str
    schedule_inventory: str
    schedule_date: str


class EcoserviceApi:
    """Client for the unauthenticated Power BI Publish-to-web report."""

    def __init__(self, session: ClientSession, timeout: float = 30) -> None:
        self._session = session
        self._timeout = ClientTimeout(total=timeout, connect=min(timeout, 10))
        self._metadata: _Metadata | None = None

    async def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        try:
            async with asyncio.timeout(self._timeout.total):
                async with self._session.request(method, url, timeout=self._timeout, **kwargs) as response:
                    if response.status >= 400:
                        raise EcoserviceApiError(f"Power BI returned HTTP {response.status}")
                    text = await response.text()
                    if "json" in response.headers.get("Content-Type", "") or text.lstrip().startswith(("{", "[")):
                        try:
                            return json.loads(text)
                        except json.JSONDecodeError as err:
                            raise EcoserviceApiError("Power BI returned invalid JSON") from err
                    return text
        except (TimeoutError, ClientError) as err:
            raise EcoserviceApiError("Unable to reach the public Ecoservice report") from err

    async def _load_metadata(self) -> _Metadata:
        if self._metadata:
            return self._metadata
        html = await self._request("GET", REPORT_URL)
        descriptor = re.search(r"resourceDescriptor\s*=\s*JSON\.parse\('(.+?)'\)", html)
        cluster = re.search(r"resolvedClusterUri\s*=\s*'([^']+)'", html)
        if not descriptor or not cluster:
            raise EcoserviceApiError("Power BI bootstrap metadata is missing")
        raw = descriptor.group(1).replace('\\"', '"')
        resource_key = json.loads(raw)["k"]
        api_cluster = cluster.group(1).replace("-redirect", "-api").rstrip("/")
        headers = self._headers(resource_key)
        models, schema = await asyncio.gather(
            self._request(
                "GET",
                f"{api_cluster}/public/reports/{resource_key}/modelsAndExploration?preferReadOnlySession=true",
                headers=headers,
            ),
            self._request(
                "GET",
                f"{api_cluster}/public/reports/{resource_key}/conceptualschema",
                headers=headers,
            ),
        )
        dataset_id = str(models["models"][0]["id"])
        fields = self._discover_fields(schema)
        self._metadata = _Metadata(api_cluster, resource_key, dataset_id, *fields)
        return self._metadata

    @staticmethod
    def _headers(key: str) -> dict[str, str]:
        activity = str(uuid4())
        return {
            "X-PowerBI-ResourceKey": key,
            "ActivityId": activity,
            "RequestId": str(uuid4()),
            "Origin": "https://app.powerbi.com",
            "User-Agent": "HomeAssistant-Ecoservice/0.1",
        }

    @staticmethod
    def _discover_fields(
        schema: dict[str, Any],
    ) -> tuple[
        str,
        str,
        str,
        str,
        str,
        str | None,
        str,
        str,
        str,
        str,
        str,
    ]:
        raw = schema.get("model") or schema.get("schemas") or schema
        text = json.dumps(raw, ensure_ascii=False)
        candidates: list[tuple[str, list[str]]] = []

        def walk(node: Any, entity: str = "") -> None:
            if isinstance(node, dict):
                current = str(node.get("name") or node.get("Name") or entity)
                props = node.get("properties") or node.get("Properties")
                if isinstance(props, list):
                    names = [str(x.get("name") or x.get("Name")) for x in props if isinstance(x, dict)]
                    candidates.append((current, names))
                for value in node.values():
                    walk(value, current)
            elif isinstance(node, list):
                for value in node:
                    walk(value, entity)

        walk(raw)
        aliases = {
            "municipality": ("sav", "savivaldyb"),
            "address": ("adres",),
            "inventory": ("invent",),
            "collection": ("aptarn", "data", "date"),
            "capacity": ("talp", "capacity"),
        }

        def pick(names: list[str], keys: Iterable[str]) -> str | None:
            return next((n for n in names if any(k in n.casefold() for k in keys)), None)

        source_fields = None
        schedule_fields = None
        for entity, names in candidates:
            municipality = next(
                (name for name in names if name.casefold().rstrip(".") in {"sav", "savivaldybė"}),
                next((name for name in names if "sav" in name.casefold() and "code" not in name.casefold()), None),
            )
            address = pick(names, aliases["address"])
            inventory = pick(names, aliases["inventory"])
            collection_date = pick(names, aliases["collection"])
            if source_fields is None and municipality and address and inventory and collection_date:
                source_fields = (
                    entity,
                    municipality,
                    address,
                    inventory,
                    collection_date,
                    pick(names, aliases["capacity"]),
                )
            exact_date = next(
                (name for name in names if name.casefold().strip() in {"date", "data"}),
                None,
            )
            if municipality and address and inventory and exact_date:
                schedule_fields = (
                    entity,
                    municipality,
                    address,
                    inventory,
                    exact_date,
                )
        if source_fields:
            if schedule_fields is None:
                schedule_fields = (
                    source_fields[0],
                    source_fields[1],
                    source_fields[2],
                    source_fields[3],
                    source_fields[4],
                )
            return (*source_fields, *schedule_fields)
        raise EcoserviceApiError(f"Required report fields were not found (schema size {len(text)})")

    async def _query(
        self,
        columns: list[str],
        filters: dict[str, str] | None = None,
        count: int = 10000,
        entity: str | None = None,
    ) -> list[list[Any]]:
        meta = await self._load_metadata()
        source = "e"
        selects = [
            {"Column": {"Expression": {"SourceRef": {"Source": source}}, "Property": p}, "Name": f"{source}.{p}"}
            for p in columns
        ]
        where = []
        for prop, value in (filters or {}).items():
            where.append(
                {
                    "Condition": {
                        "In": {
                            "Expressions": [
                                {"Column": {"Expression": {"SourceRef": {"Source": source}}, "Property": prop}}
                            ],
                            "Values": [[{"Literal": {"Value": powerbi_string_literal(value)}}]],
                        }
                    }
                }
            )
        query: dict[str, Any] = {
            "Version": 2,
            "From": [{"Name": source, "Entity": entity or meta.entity, "Type": 0}],
            "Select": selects,
        }
        if where:
            query["Where"] = where
        payload = {
            "version": "1.0.0",
            "queries": [
                {
                    "Query": {
                        "Commands": [
                            {
                                "SemanticQueryDataShapeCommand": {
                                    "Query": query,
                                    "Binding": {
                                        "DataReduction": {"DataVolume": 6, "Primary": {"Window": {"Count": count}}},
                                        "Primary": {
                                            "Groupings": [{"Projections": list(range(len(columns))), "Subtotal": 1}]
                                        },
                                    },
                                    "ExecutionMetricsKind": 1,
                                }
                            }
                        ]
                    }
                }
            ],
            "cancelQueries": [],
            "modelId": meta.dataset_id,
        }
        data = await self._request(
            "POST",
            f"{meta.cluster}/public/reports/querydata?synchronous=true",
            headers={**self._headers(meta.resource_key), "Content-Type": "application/json"},
            json=payload,
        )
        try:
            data_set = data["results"][0]["result"]["data"]["dsr"]["DS"][0]
            rows = data_set.get("PH", [{}])[0].get("DM0", [])
        except (KeyError, IndexError, TypeError) as err:
            raise EcoserviceApiError("Unexpected Power BI query response") from err
        value_dictionaries = data_set.get("ValueDicts", {})
        column_dictionaries: dict[int, list[Any]] = {}
        if rows:
            for descriptor in rows[0].get("S", []):
                name = str(descriptor.get("N", ""))
                dictionary_name = descriptor.get("DN")
                if name.startswith("G") and dictionary_name in value_dictionaries:
                    column_dictionaries[int(name[1:])] = value_dictionaries[dictionary_name]

        def decode(column: int, value: Any) -> Any:
            dictionary = column_dictionaries.get(column)
            if dictionary is not None and isinstance(value, int) and 0 <= value < len(dictionary):
                return dictionary[value]
            return value

        result, previous = [], [None] * len(columns)
        for row in rows:
            direct = [decode(col, row.get(f"G{col}")) for col in range(len(columns))]
            if any(value is not None for value in direct):
                previous = [value if value is not None else previous[col] for col, value in enumerate(direct)]
                result.append(list(previous))
                continue
            values, index = list(previous), 0
            repeats = row.get("R", 0)
            for col in range(len(columns)):
                if repeats & (1 << col):
                    continue
                if index < len(row.get("C", [])):
                    values[col] = decode(col, row["C"][index])
                index += 1
            previous = values
            result.append(values)
        return result

    async def municipalities(self) -> list[str]:
        meta = await self._load_metadata()
        return sorted({str(r[0]).strip() for r in await self._query([meta.municipality]) if r[0]})

    async def addresses(self, municipality: str, search: str | None = None) -> list[str]:
        meta = await self._load_metadata()
        rows = await self._query(
            [meta.address],
            {meta.municipality: municipality},
            count=ADDRESS_QUERY_LIMIT,
        )
        values = sorted({str(r[0]).strip() for r in rows if r[0]}, key=natural_sort_key)
        if search:
            normalized_search = normalize_search_text(search)
            values = [value for value in values if normalize_search_text(value).startswith(normalized_search)]
        return values

    async def containers(self, municipality: str, address: str) -> list[Container]:
        meta = await self._load_metadata()
        columns = [meta.inventory] + ([meta.capacity] if meta.capacity else [])
        rows = await self._query(columns, {meta.municipality: municipality, meta.address: address})
        found = {str(r[0]).strip(): (str(r[1]) if len(r) > 1 and r[1] else None) for r in rows if r[0]}
        return [Container(k, waste_type_from_inventory(k), v) for k, v in sorted(found.items())]

    async def schedules(self, municipality: str, address: str, inventories: list[str]) -> dict[str, Schedule]:
        meta = await self._load_metadata()
        rows = await self._query(
            [meta.schedule_inventory, meta.schedule_date],
            {
                meta.schedule_municipality: municipality,
                meta.schedule_address: address,
            },
            entity=meta.schedule_entity,
        )
        grouped: dict[str, list[Any]] = {item: [] for item in inventories}
        for inventory, value in rows:
            if str(inventory) in grouped:
                grouped[str(inventory)].append(value)
        result = {
            i: Schedule(Container(i, waste_type_from_inventory(i)), normalize_dates(values))
            for i, values in grouped.items()
        }
        if not any(schedule.dates for schedule in result.values()):
            raise EcoserviceNotFound("No collection dates were found")
        return result
