from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, List

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfVolume
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr

from .const import (
    DOMAIN,
    ATTR_TOKEN_EXPIRES_AT,
    # ATTR_TOKEN_EXPIRES_IN,  # intentionally unused
    ATTR_COOKIE_PRESENT,
)
from .coordinator import CEMAuthCoordinator
from .userinfo_coordinator import CEMUserInfoCoordinator
from .meter_counters_coordinator import CEMMeterCountersCoordinator
from .water_coordinator import CEMWaterCoordinator


def _slug_int(v: Optional[int]) -> str:
    return str(v) if v is not None else "unknown"


def _slug_text(s: Optional[str]) -> str:
    if not isinstance(s, str) or not s.strip():
        return "unknown"
    out = []
    for ch in s.strip().lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", ".", "/"):
            out.append("_")
        else:
            out.append("_")
    slug = "".join(out)
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_") or "unknown"


async def async_setup_entry(hass, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    auth: CEMAuthCoordinator = data["coordinator"]
    ui: CEMUserInfoCoordinator = data["userinfo"]

    entities: list[SensorEntity] = [
        CEMApiStatusSensor(auth, ui, entry),
        CEMAccountSensor(ui, entry),
    ]

    meters_map: dict[int, dict] = data.get("meters_map", {})
    # Create only WATER sensors per meter/var, attached to the OBJECT device (mis).
    for me_id, meta in meters_map.items():
        counters: CEMMeterCountersCoordinator = meta["counters"]
        me_serial: Optional[str] = meta.get("me_serial")
        mis_id: Optional[int] = meta.get("mis_id")
        mis_name: Optional[str] = meta.get("mis_name")

        water_map: dict[int, CEMWaterCoordinator] = meta.get("water", {})
        for vid, wc in water_map.items():
            entities.append(
                CEMWaterSensor(
                    wc, counters, ui, entry,
                    me_id=me_id, var_id=vid,
                    me_serial=me_serial, mis_id=mis_id, mis_name=mis_name
                )
            )

    async_add_entities(entities)


class _DeviceInfoHelper:
    @staticmethod
    def account_label(ui_data: dict[str, Any]) -> tuple[Optional[int], Optional[str]]:
        return ui_data.get("company_id"), (ui_data.get("display_name") or ui_data.get("company"))

    @staticmethod
    def desired_account_name(label: Optional[str]) -> str:
        # Device name must be EXACTLY "CEM Account <label>" (no company ID here)
        if label and label.strip():
            return f"CEM Account {label.strip()}"
        return "CEM Account"

    @staticmethod
    def desired_object_name(mis_name: Optional[str], mis_id: Optional[int]) -> str:
        if isinstance(mis_name, str) and mis_name.strip():
            return f"CEM Object {mis_name.strip()}"
        if mis_id is not None:
            return f"CEM Object {mis_id}"
        return "CEM Object"

    @staticmethod
    def build_account(entry: ConfigEntry, company_id: Optional[int], label: Optional[str]) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id, "account")},
            name=_DeviceInfoHelper.desired_account_name(label),
            manufacturer="CEM",
            model="Unofficial API",
        )

    @staticmethod
    def build_object(
        entry: ConfigEntry,
        company_id: Optional[int],
        mis_id: Optional[int],
        mis_name: Optional[str],
    ) -> DeviceInfo:
        ident = (DOMAIN, entry.entry_id, f"mis:{mis_id}") if mis_id is not None else (DOMAIN, entry.entry_id, "mis:unknown")
        return DeviceInfo(
            identifiers={ident},
            name=_DeviceInfoHelper.desired_object_name(mis_name, mis_id),
            manufacturer="CEM",
            model="Unofficial API",
        )


class CEMApiStatusSensor(CoordinatorEntity[CEMAuthCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Status"
    _attr_icon = "mdi:cloud-check-variant"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: CEMAuthCoordinator, ui: CEMUserInfoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._ui = ui
        self._attr_unique_id = f"{entry.entry_id}_api_status"
        company_id = (self._ui.data or {}).get("company_id")
        # Keep company id in the entity_id for uniqueness across accounts:
        name_label = (self._ui.data or {}).get("display_name") or (self._ui.data or {}).get("company")
        self._attr_suggested_object_id = f"cem_account_{_slug_text(name_label)}_{_slug_int(company_id)}_status"

    async def async_added_to_hass(self) -> None:
        # Rename the account device to EXACT "CEM Account <label>"
        ui_data = self._ui.data or {}
        _company_id, label = _DeviceInfoHelper.account_label(ui_data)
        desired = _DeviceInfoHelper.desired_account_name(label)

        devreg = dr.async_get(self.hass)
        device = devreg.async_get_device(identifiers={(DOMAIN, self._entry.entry_id, "account")})
        if device and device.name != desired:
            devreg.async_update_device(device.id, name=desired)

    @property
    def device_info(self) -> DeviceInfo:
        ui_data = self._ui.data or {}
        company_id, label = _DeviceInfoHelper.account_label(ui_data)
        return _DeviceInfoHelper.build_account(self._entry, company_id, label)

    @property
    def native_value(self) -> str:
        data = self.coordinator.data or {}
        connected = data.get("connected", False)
        expires_at = self.coordinator.token_expires_at
        if expires_at and datetime.now(timezone.utc) >= expires_at:
            connected = False
        return "connected" if connected else "disconnected"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # Connection-only attributes
        data = self.coordinator.data or {}
        return {
            ATTR_TOKEN_EXPIRES_AT: data.get("token_expires_at_iso"),
            ATTR_COOKIE_PRESENT: data.get("cookie_present"),
        }


class CEMAccountSensor(CoordinatorEntity[CEMUserInfoCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Account"
    _attr_icon = "mdi:account-badge"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: CEMUserInfoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_account"
        # Keep company id in the entity_id for uniqueness; visible name remains just "Account"
        company_id = (self.coordinator.data or {}).get("company_id")
        name_label = (self.coordinator.data or {}).get("display_name") or (self.coordinator.data or {}).get("company")
        self._attr_suggested_object_id = f"cem_account_{_slug_text(name_label)}_{_slug_int(company_id)}_account"

    async def async_added_to_hass(self) -> None:
        ui_data = self.coordinator.data or {}
        _company_id, label = _DeviceInfoHelper.account_label(ui_data)
        desired = _DeviceInfoHelper.desired_account_name(label)

        devreg = dr.async_get(self.hass)
        device = devreg.async_get_device(identifiers={(DOMAIN, self._entry.entry_id, "account")})
        if device and device.name != desired:
            devreg.async_update_device(device.id, name=desired)

    @property
    def device_info(self) -> DeviceInfo:
        data = self.coordinator.data or {}
        company_id, label = _DeviceInfoHelper.account_label(data)
        return _DeviceInfoHelper.build_account(self._entry, company_id, label)

    @property
    def native_value(self) -> str:
        data = self.coordinator.data or {}
        return str(data.get("display_name") or data.get("company") or "ok")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # Only concise, non-array, no raw blobs
        d = self.coordinator.data or {}
        return {
            "company_id": d.get("company_id"),
            "customer_id": d.get("customer_id"),
            "person_id": d.get("person_id"),
            "company_name": d.get("company"),
            "display_name": d.get("display_name"),
            "login_valid_from": d.get("login_valid_from"),
            "login_valid_to": d.get("login_valid_to"),
        }


# WATER device class fallback
try:
    _WATER_DEVICE_CLASS = SensorDeviceClass.WATER
except Exception:
    _WATER_DEVICE_CLASS = SensorDeviceClass.VOLUME


class CEMWaterSensor(CoordinatorEntity[CEMWaterCoordinator], SensorEntity):
    """Water reading per var_id, attached to the Object device and named 'Water [SN]'."""

    _attr_force_update = True
    _attr_has_entity_name = True
    _attr_icon = "mdi:water"
    # PRIMARY entity (no diagnostic category)
    _attr_device_class = _WATER_DEVICE_CLASS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
    _attr_suggested_display_precision = 3

    def __init__(
        self,
        coordinator: CEMWaterCoordinator,
        counters: CEMMeterCountersCoordinator,
        ui: CEMUserInfoCoordinator,
        entry: ConfigEntry,
        me_id: int,
        var_id: int,
        me_serial: Optional[str],
        mis_id: Optional[int],
        mis_name: Optional[str],
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._counters = counters
        self._ui = ui
        self._me_id = int(me_id)
        self._var_id = int(var_id)
        self._me_serial = me_serial
        self._mis_id = mis_id
        self._mis_name = mis_name

        label = me_serial if (isinstance(me_serial, str) and me_serial.strip()) else f"me{me_id}"
        self._attr_name = f"Water [{label}]"
        self._attr_unique_id = f"{entry.entry_id}_mis_{mis_id}_me_{me_id}_var_{var_id}"

        mis_slug = _slug_text(mis_name if isinstance(mis_name, str) and mis_name.strip() else str(mis_id))
        self._attr_suggested_object_id = f"cem_object_{mis_slug}_water_{label}_{var_id}"

    async def async_added_to_hass(self) -> None:
        # Ensure the Object device has the desired name
        devreg = dr.async_get(self.hass)
        device = devreg.async_get_device(identifiers={(DOMAIN, self._entry.entry_id, f"mis:{self._mis_id}")})
        desired = _DeviceInfoHelper.desired_object_name(self._mis_name, self._mis_id)
        if device and device.name != desired:
            devreg.async_update_device(device.id, name=desired)

    @property
    def device_info(self) -> DeviceInfo:
        return _DeviceInfoHelper.build_object(self._entry, (self._ui.data or {}).get("company_id"), self._mis_id, self._mis_name)

    def _meta(self) -> tuple[Optional[str], Optional[str]]:
        counters = (self._counters.data or {}).get("counters") or []
        for c in counters:
            try:
                if int(c.get("var_id")) == self._var_id:
                    return c.get("name"), c.get("unit")
            except Exception:
                continue
        return None, None

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data or {}
        value = data.get("value")
        if value is None:
            return None
        _name, unit = self._meta()
        if isinstance(unit, str) and unit.strip().lower() in {"l", "liter", "litre", "liters", "litres"}:
            try:
                return float(value) / 1000.0  # liters -> m³
            except Exception:
                return value
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Clean, useful attributes only."""
        data = self.coordinator.data or {}
        name, unit = self._meta()
        company_id = (self._ui.data or {}).get("company_id")

        last_poll_ms = data.get("fetched_at")
        last_poll_iso = (
            datetime.fromtimestamp(int(last_poll_ms) / 1000, tz=timezone.utc).isoformat()
            if last_poll_ms is not None else None
        )

        return {
            "company_id": company_id,
            "object_id": (self._counters.data or {}).get("mis_id"),
            "object_name": self._mis_name,
            "meter_id": self._me_id,
            "meter_serial": self._me_serial,
            "counter_id": self._var_id,
            "counter_name": name,
            "reported_unit": unit,
            "reading_timestamp": data.get("timestamp_iso"),
            "reading_timestamp_ms": data.get("timestamp_ms"),
            "last_poll": last_poll_iso,
            "last_poll_ms": last_poll_ms,
        }