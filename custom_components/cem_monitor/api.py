from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from .const import (
    AUTH_URL,
    COUNTER_LAST_URL,
    COUNTER_VALUE_TYPES_URL,
    COUNTERS_BY_METER_URL,
    COUNTERS_BY_OBJECT_URL,
    METERS_URL,
    OBJECTS_URL,
    USERINFO_URL,
)
from .utils.retry import async_retry_with_backoff

_LOGGER = logging.getLogger(__name__)


@dataclass
class AuthResult:
    access_token: str
    valid_to_ms: int
    cookie_value: str | None


def _coerce_list(payload: Any, endpoint: str) -> list[dict[str, Any]]:
    """Accept either a top-level list or an object with 'data': [...]."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return data
    raise ValueError(f"{endpoint} returned unexpected structure")


class CEMClient:
    """Async client for CEM auth + objects + meters + counters + readings."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def authenticate(self, username: str, password: str) -> AuthResult:
        data = {"user": username, "pass": password}
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        timeout = ClientTimeout(total=20)

        async def _do_authenticate() -> AuthResult:
            _LOGGER.debug("CEM auth: POST %s", AUTH_URL)
            async with self._session.post(
                AUTH_URL, data=data, headers=headers, timeout=timeout
            ) as resp:
                resp.raise_for_status()
                text = await resp.text()
                _LOGGER.debug("CEM auth: HTTP %s", resp.status)
                _LOGGER.debug("CEM auth: raw body (first 300 chars): %s", text[:300])
                payload = await resp.json(content_type=None)

                token = payload.get("access_token")
                valid_to_raw = payload.get("valid_to")
                if token is None or valid_to_raw is None:
                    raise ValueError("CEM auth response missing access_token or valid_to")

                valid_to_ms = int(valid_to_raw)
                cookie_val = (
                    resp.cookies["CEMAPI"].value
                    if resp.cookies and "CEMAPI" in resp.cookies
                    else None
                )
                _LOGGER.debug(
                    "CEM auth: CEMAPI cookie %s", "present" if cookie_val else "NOT present"
                )
                return AuthResult(
                    access_token=token, valid_to_ms=valid_to_ms, cookie_value=cookie_val
                )

        return await async_retry_with_backoff(_do_authenticate, context="CEM auth")

    async def _auth_headers(self, token: str, cookie: str | None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if cookie:
            headers["Cookie"] = f"CEMAPI={cookie}"
        return headers

    async def get_user_info(self, token: str, cookie: str | None) -> dict[str, Any]:
        headers = await self._auth_headers(token, cookie)
        timeout = ClientTimeout(total=20)

        async def _do_get_user_info() -> dict[str, Any]:
            _LOGGER.debug("CEM getUserInfo: GET %s", USERINFO_URL)
            async with self._session.get(USERINFO_URL, headers=headers, timeout=timeout) as resp:
                resp.raise_for_status()
                text = await resp.text()
                _LOGGER.debug("CEM getUserInfo: HTTP %s", resp.status)
                _LOGGER.debug("CEM getUserInfo: raw body (first 300 chars): %s", text[:300])
                payload = await resp.json(content_type=None)
                if not isinstance(payload, dict):
                    raise ValueError("getUserInfo returned unexpected data structure")
                return payload

        return await async_retry_with_backoff(_do_get_user_info, context="CEM getUserInfo")

    async def get_objects(self, token: str, cookie: str | None) -> list[dict[str, Any]]:
        """GET id=23: returns list of objects with mis_id (and typically a name/label)."""
        headers = await self._auth_headers(token, cookie)
        timeout = ClientTimeout(total=20)

        async def _do_get_objects() -> list[dict[str, Any]]:
            _LOGGER.debug("CEM objects: GET %s", OBJECTS_URL)
            async with self._session.get(OBJECTS_URL, headers=headers, timeout=timeout) as resp:
                resp.raise_for_status()
                text = await resp.text()
                _LOGGER.debug("CEM objects: HTTP %s", resp.status)
                _LOGGER.debug("CEM objects: raw body (first 300 chars): %s", text[:300])
                payload = await resp.json(content_type=None)
                # Most commonly a list; allow {"data":[...]} just in case
                items = _coerce_list(payload, "id=23")
                return items

        return await async_retry_with_backoff(_do_get_objects, context="CEM objects")

    async def get_meters(
        self, token: str, cookie: str | None, mis_id: int | None = None
    ) -> list[dict[str, Any]]:
        """GET id=108: returns meters (me_id, typically with mis_id).
        Accepts both top-level list and {"data":[...]} wrapper.
        If mis_id is provided, attempt server-side filter and then enforce client-side filter.
        """
        headers = await self._auth_headers(token, cookie)

        async def _fetch(url: str) -> list[dict[str, Any]]:
            timeout = ClientTimeout(total=20)

            async def _do_fetch() -> list[dict[str, Any]]:
                _LOGGER.debug("CEM meters: GET %s", url)
                async with self._session.get(url, headers=headers, timeout=timeout) as resp:
                    resp.raise_for_status()
                    text = await resp.text()
                    _LOGGER.debug("CEM meters: HTTP %s", resp.status)
                    _LOGGER.debug("CEM meters: raw body (first 300 chars): %s", text[:300])
                    payload = await resp.json(content_type=None)
                    return _coerce_list(payload, "id=108")

            return await async_retry_with_backoff(_do_fetch, context=f"CEM meters({url})")

        items: list[dict[str, Any]] = []
        if mis_id is not None:
            for param in ("mis_id", "misid", "misId"):
                url = f"{METERS_URL}&{param}={int(mis_id)}"
                try:
                    items = await _fetch(url)
                    break
                except Exception as err:
                    _LOGGER.debug("CEM meters(mis=%s): try %s failed: %s", mis_id, param, err)
        if not items:
            # fallback: fetch all
            items = await _fetch(METERS_URL)

        # client-side filter by mis_id if provided and present on items
        if mis_id is not None:

            def _extract_mis(it: dict[str, Any]) -> int | None:
                for k in ("mis_id", "misid", "misId", "object_id", "obj_id"):
                    if k in it:
                        try:
                            return int(it[k])
                        except Exception:
                            return None
                return None

            before = len(items)
            items = [it for it in items if _extract_mis(it) == int(mis_id)]
            _LOGGER.debug(
                "CEM meters: filtered by mis_id=%s (%d -> %d)", mis_id, before, len(items)
            )

        return items

    async def get_counters_by_meter(
        self, me_id: int, token: str, cookie: str | None
    ) -> list[dict[str, Any]]:
        """GET id=107 for a given me_id: returns counters with var_id and full meta.
        Accepts both top-level list and {"data":[...]} wrapper.
        """
        headers = await self._auth_headers(token, cookie)

        async def _fetch(url: str) -> list[dict[str, Any]]:
            timeout = ClientTimeout(total=20)

            async def _do_fetch() -> list[dict[str, Any]]:
                _LOGGER.debug("CEM counters(me=%s): GET %s", me_id, url)
                async with self._session.get(url, headers=headers, timeout=timeout) as resp:
                    resp.raise_for_status()
                    text = await resp.text()
                    _LOGGER.debug("CEM counters(me=%s): HTTP %s", me_id, resp.status)
                    _LOGGER.debug(
                        "CEM counters(me=%s): raw body (first 300 chars): %s", me_id, text[:300]
                    )
                    payload = await resp.json(content_type=None)
                    return _coerce_list(payload, "id=107")

            return await async_retry_with_backoff(_do_fetch, context=f"CEM counters(me={me_id})")

        tried = []
        for param in ("me_id", "meid", "meId"):
            url = f"{COUNTERS_BY_METER_URL}&{param}={int(me_id)}"
            tried.append(url)
            try:
                items = await _fetch(url)

                # Safety: enforce me_id on items if present
                def _extract_me(it: dict[str, Any]) -> int | None:
                    for k in ("me_id", "meid", "meId"):
                        if k in it:
                            try:
                                return int(it[k])
                            except Exception:
                                return None
                    return None

                if any(_extract_me(it) is not None for it in items):
                    before = len(items)
                    items = [it for it in items if _extract_me(it) == int(me_id)]
                    _LOGGER.debug(
                        "CEM counters: filtered by me_id=%s (%d -> %d)", me_id, before, len(items)
                    )

                return items
            except Exception as err:
                _LOGGER.debug("CEM counters(me=%s): try %s failed: %s", me_id, param, err)

        raise ValueError(f"id=107 failed for me_id={me_id}; tried: {tried}")

    async def get_counters_for_object(
        self, mis_id: int, token: str, cookie: str | None
    ) -> list[dict[str, Any]]:
        """GET id=45 for a given mis_id: returns counters with var_id and full meta.
        Accepts both top-level list and {"data":[...]} wrapper.
        """
        headers = await self._auth_headers(token, cookie)

        async def _fetch(url: str) -> list[dict[str, Any]]:
            timeout = ClientTimeout(total=20)

            async def _do_fetch() -> list[dict[str, Any]]:
                _LOGGER.debug("CEM counters(mis=%s): GET %s", mis_id, url)
                async with self._session.get(url, headers=headers, timeout=timeout) as resp:
                    resp.raise_for_status()
                    text = await resp.text()
                    _LOGGER.debug("CEM counters(mis=%s): HTTP %s", mis_id, resp.status)
                    _LOGGER.debug(
                        "CEM counters(mis=%s): raw body (first 300 chars): %s", mis_id, text[:300]
                    )
                    payload = await resp.json(content_type=None)
                    return _coerce_list(payload, "id=45")

            return await async_retry_with_backoff(_do_fetch, context=f"CEM counters(mis={mis_id})")

        tried = []
        for param in ("mis_id", "misid", "misId"):
            url = f"{COUNTERS_BY_OBJECT_URL}&{param}={int(mis_id)}"
            tried.append(url)
            try:
                items = await _fetch(url)
                return items
            except Exception as err:
                _LOGGER.debug("CEM counters(mis=%s): try %s failed: %s", mis_id, param, err)

        raise ValueError(f"id=45 failed for mis_id={mis_id}; tried: {tried}")

    async def get_counter_reading(
        self, var_id: int, token: str, cookie: str | None
    ) -> dict[str, Any]:
        """GET id=8 for a given var_id -> {'value': float, 'timestamp_ms': int}"""
        headers = await self._auth_headers(token, cookie)

        url = f"{COUNTER_LAST_URL}&var_id={int(var_id)}"
        timeout = ClientTimeout(total=20)

        async def _do_get_counter_reading() -> dict[str, Any]:
            _LOGGER.debug("CEM counter: GET %s", url)
            async with self._session.get(url, headers=headers, timeout=timeout) as resp:
                resp.raise_for_status()
                text = await resp.text()
                _LOGGER.debug("CEM counter: HTTP %s", resp.status)
                _LOGGER.debug("CEM counter: raw body (first 300 chars): %s", text[:300])
                payload = await resp.json(content_type=None)

                # id=8 is typically a list; be lenient if it ever wraps into {"data":[...]}
                readings = payload
                if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                    readings = payload["data"]

                if not isinstance(readings, list) or not readings:
                    raise ValueError(f"id=8 unexpected response: {payload!r}")

                reading = readings[0]  # newest first
                value = reading.get("value")
                ts_ms = reading.get("timestamp")
                if value is None or ts_ms is None:
                    raise ValueError(f"id=8 missing fields: {reading!r}")

                return {"value": float(value), "timestamp_ms": int(ts_ms)}

        return await async_retry_with_backoff(
            _do_get_counter_reading, context=f"CEM counter(var_id={var_id})"
        )

    async def get_counter_readings_batch(
        self, var_ids: list[int], token: str, cookie: str | None
    ) -> dict[int, dict[str, Any]]:
        """POST id=8 with batch var_ids -> {var_id: {'value': float, 'timestamp_ms': int}}"""
        headers = await self._auth_headers(token, cookie)
        headers["Content-Type"] = "application/json"

        url = COUNTER_LAST_URL  # https://cemapi.unimonitor.eu/api?id=8
        body = [{"var_id": int(vid)} for vid in var_ids]
        timeout = ClientTimeout(total=20)

        async def _do_get_counter_readings_batch() -> dict[int, dict[str, Any]]:
            _LOGGER.debug("CEM counter batch: POST %s with %d var_ids", url, len(var_ids))
            async with self._session.post(url, json=body, headers=headers, timeout=timeout) as resp:
                resp.raise_for_status()
                text = await resp.text()
                _LOGGER.debug("CEM counter batch: HTTP %s", resp.status)
                _LOGGER.debug("CEM counter batch: raw body (first 300 chars): %s", text[:300])
                payload = await resp.json(content_type=None)

                # Response is an array of objects: [{"value": float, "timestamp": int, "var_id": int}, ...]
                readings = payload
                if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                    readings = payload["data"]

                if not isinstance(readings, list):
                    raise ValueError(f"id=8 batch unexpected response: {payload!r}")

                # Handle empty batch responses
                if not readings and var_ids:
                    _LOGGER.warning(
                        "CEM counter batch: API returned empty list for %d requested var_ids: %s",
                        len(var_ids),
                        sorted(var_ids),
                    )
                    return {}

                # Build result dictionary mapping var_id -> reading data
                result: dict[int, dict[str, Any]] = {}
                for reading in readings:
                    var_id_raw = reading.get("var_id")
                    if var_id_raw is None:
                        _LOGGER.warning("CEM counter batch: reading missing var_id: %r", reading)
                        continue

                    try:
                        var_id = int(var_id_raw)
                    except (ValueError, TypeError):
                        _LOGGER.warning("CEM counter batch: invalid var_id in reading: %r", reading)
                        continue

                    value = reading.get("value")
                    ts_ms = reading.get("timestamp")
                    if value is None or ts_ms is None:
                        _LOGGER.warning(
                            "CEM counter batch: reading missing value or timestamp: %r", reading
                        )
                        continue

                    result[var_id] = {"value": float(value), "timestamp_ms": int(ts_ms)}

                # Log any missing var_ids
                requested_set = {int(vid) for vid in var_ids}
                received_set = set(result.keys())
                missing = requested_set - received_set
                if missing:
                    _LOGGER.warning(
                        "CEM counter batch: %d var_ids not in response: %s",
                        len(missing),
                        sorted(missing),
                    )
                else:
                    _LOGGER.debug("CEM counter batch: received all %d var_ids", len(var_ids))

                return result

        return await async_retry_with_backoff(
            _do_get_counter_readings_batch, context=f"CEM counter batch({len(var_ids)} var_ids)"
        )

    async def get_pot_types(
        self,
        token: str,
        cookie: str | None,
    ) -> dict:
        """Get global pot/unit types list (id=222)."""
        url = "https://cemapi.unimonitor.eu/api?id=222"

        headers = await self._auth_headers(token, cookie)
        timeout = ClientTimeout(total=20)

        async def _do_get_pot_types() -> dict:
            _LOGGER.debug("CEM API: GET %s", url)
            async with self._session.get(url, headers=headers, timeout=timeout) as resp:
                resp.raise_for_status()
                text = await resp.text()
                _LOGGER.debug(
                    "CEM pot_types: HTTP %s, raw body (first 300 chars): %s",
                    resp.status,
                    text[:300],
                )
                data = await resp.json(content_type=None)
                return data if isinstance(data, dict) else {}

        return await async_retry_with_backoff(_do_get_pot_types, context="CEM pot_types")

    async def get_counter_value_types(
        self,
        token: str,
        cookie: str | None,
        cis: int = 50,
    ) -> dict:
        """Get counter value types list (id=11&cis=50)."""
        url = f"{COUNTER_VALUE_TYPES_URL}&cis={int(cis)}"

        headers = await self._auth_headers(token, cookie)
        timeout = ClientTimeout(total=20)

        async def _do_get_counter_value_types() -> dict:
            _LOGGER.debug("CEM API: GET %s", url)
            async with self._session.get(url, headers=headers, timeout=timeout) as resp:
                resp.raise_for_status()
                text = await resp.text()
                _LOGGER.debug(
                    "CEM counter_value_types: HTTP %s, raw body (first 300 chars): %s",
                    resp.status,
                    text[:300],
                )
                data = await resp.json(content_type=None)
                return data if isinstance(data, dict) else {}

        return await async_retry_with_backoff(
            _do_get_counter_value_types, context="CEM counter_value_types"
        )
