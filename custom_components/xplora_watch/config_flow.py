"""Config flow for Xplora® Watch Version 2."""

from __future__ import annotations

import logging
from collections import OrderedDict
from types import MappingProxyType
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries, core
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.const import (
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CONF_COUNTRY_CODE,
    CONF_EMAIL,
    CONF_LANGUAGE,
    CONF_PASSWORD,
    CONF_RADIUS,
    CONF_SCAN_INTERVAL,
    STATE_OFF,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import SectionConfig, section
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .config import resolve_account_alias, resolve_language
from .const import (
    CONF_ACCOUNT_ALIAS,
    CONF_AUTO_FETCH_HISTORY,
    CONF_AUTO_MARK_READ,
    CONF_HISTORY_RETENTION_DAYS,
    CONF_HOME_LATITUDE,
    CONF_HOME_LONGITUDE,
    CONF_HOME_RADIUS,
    CONF_HOME_SAFEZONE,
    CONF_MAPS,
    CONF_MESSAGE,
    CONF_NOTIFY_CALL,
    CONF_NOTIFY_LOW_POWER,
    CONF_NOTIFY_POWER,
    CONF_NOTIFY_SOS,
    CONF_OPENCAGE_APIKEY,
    CONF_PHONENUMBER,
    CONF_REFRESH_ON_CARD_RENDER,
    CONF_REMOVE_MESSAGE,
    CONF_SCAN_INTERVAL_FUNCTIONS,
    CONF_SIGNIN_TYP,
    CONF_TIMEZONE,
    CONF_USERLANG,
    CONF_WATCHES,
    DEFAULT_AUTO_FETCH_HISTORY,
    DEFAULT_HISTORY_RETENTION_DAYS,
    DEFAULT_HOME_RADIUS,
    DEFAULT_LANGUAGE,
    DEFAULT_REFRESH_ON_CARD_RENDER,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_FUNCTIONS,
    DOMAIN,
    HISTORY_RETENTION_DAYS_MAX,
    HISTORY_RETENTION_DAYS_MIN,
    HOME,
    HOME_SAFEZONE,
    MAPS,
    OPTIONS_SECTIONS,
    SCAN_INTERVAL_FUNCTIONS_OPTIONS,
    SCAN_INTERVAL_OPTIONS,
    SECTION_CHAT,
    SECTION_GENERAL,
    SECTION_HISTORY,
    SECTION_LOCATION,
    SECTION_NOTIFICATIONS,
    SECTION_POLLING,
    SECTION_WATCHES,
    SIGNIN,
    SUPPORTED_LANGUAGES,
    normalize_history_retention_days,
    normalize_scan_interval,
    normalize_scan_interval_functions,
)
from .const_schema import DATA_SCHEMA_EMAIL, DATA_SCHEMA_PHONE
from .demo import make_controller
from .helper import watch_user_label
from .pyxplora_api.exception_classes import AuthError, Error, LoginError, PhoneOrEmailFail, RateLimitError
from .pyxplora_api.pyxplora_api_async import PyXploraApi
from .pyxplora_api.status import UserContactType

_LOGGER = logging.getLogger(__name__)


@callback
async def sign_in(hass: core.HomeAssistant, data: dict[str, Any] | MappingProxyType[str, Any]) -> PyXploraApi:
    """Sign in to the Xplora® API."""
    controller: PyXploraApi = make_controller(
        countrycode=data.get(CONF_COUNTRY_CODE) or "",
        phoneNumber=data.get(CONF_PHONENUMBER) or "",
        password=data.get(CONF_PASSWORD, ""),
        userLang=data.get(CONF_USERLANG) or "",
        timeZone=data.get(CONF_TIMEZONE) or "",
        email=data.get(CONF_EMAIL, None),
        session=aiohttp_client.async_get_clientsession(hass),
    )
    await controller.init()
    return controller


async def validate_input(hass: core.HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Validate the user input allows us to connect.

    Data has the keys from DATA_SCHEMA with values provided by the user.
    """

    # No `init()` here: `checkEmailOrPhoneExist` runs under OPEN authorization (static API key,
    # no bearer token), so the old `account.init(signup=False)` only burned ~5 failed credential-
    # less login attempts against the rate-limit-sensitive auth endpoint for nothing.
    account = make_controller(
        session=aiohttp_client.async_create_clientsession(hass),
        email=data.get(CONF_EMAIL),
        phoneNumber=data.get(CONF_PHONENUMBER) or "",
    )
    if not await account.checkEmailOrPhoneExist(
        UserContactType.EMAIL if data.get(CONF_EMAIL) else UserContactType.PHONE,
        email=data.get(CONF_EMAIL) or "",
        countryCode=data.get(CONF_COUNTRY_CODE) or "",
        phoneNumber=data.get(CONF_PHONENUMBER) or "",
    ):
        raise PhoneOrEmailFail()

    try:
        controller = await sign_in(hass=hass, data=data)
    except LoginError as err:
        raise LoginError(err.error_message) from err

    # Return info that you want to store in the config entry. `username` is the Account display
    # name (`getUserName()`), surfaced so the following alias step can pre-fill its field with it.
    return {"username": controller.getUserName()}


def validate_options_input(user_input: dict[str, Any]) -> dict[str, str]:
    """Validate the options form before the entry is written.

    Reads every key defensively (``.get``): the schema marks some fields optional, so a value the
    selector omitted must surface as a friendly form error instead of a ``KeyError`` that would
    abort the whole options dialog with a stack trace.
    """
    errors = {}
    key: str = user_input.get(CONF_OPENCAGE_APIKEY, "")
    maps = user_input.get(CONF_MAPS, MAPS[0])

    if maps == MAPS[1] and len(key) == 0:
        errors["base"] = "api_key_error"

    if not user_input.get(CONF_WATCHES):
        errors["base"] = "no_watch"

    # Return info that you want to store in the config entry.
    return errors


class XploraConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Xplora® Watch Version 2."""

    VERSION = 1

    # Carried from the credentials step into the alias step (set once login validates). Real defaults,
    # not bare annotations, so an out-of-order step entry degrades to empty carry-over (a clean flow
    # error) instead of an AttributeError on an attribute that was never assigned.
    _account_data: dict[str, Any] = {}
    _default_alias: str = ""

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler.

        No constructor argument: `XploraOptionsFlowHandler` derives from the modern plain
        `OptionsFlow`, where HA supplies `self.config_entry` itself. The entry is still accepted
        here because HA core calls this hook with it.
        """
        return XploraOptionsFlowHandler()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        return self.async_show_menu(step_id="user", menu_options=["user_email", "user_phone"])

    async def async_step_user_phone(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            unique_id = f"{user_input[CONF_PHONENUMBER]}"

            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            info = None
            try:
                info = await validate_input(self.hass, user_input)
            except PhoneOrEmailFail as error:
                _LOGGER.exception(error)
                errors["base"] = "phone_email_invalid"
            except LoginError as error:
                _LOGGER.exception(error)
                errors["base"] = "pass_invalid"
            except Error as error:
                _LOGGER.exception(error)
                errors["base"] = "cannot_connect"

            if info:
                return self._advance_to_alias(user_input, info)

        return self.async_show_form(step_id="user_phone", data_schema=vol.Schema(DATA_SCHEMA_PHONE), errors=errors, last_step=False)

    async def async_step_user_email(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            unique_id = f"{user_input[CONF_EMAIL]}"

            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            info = None
            try:
                info = await validate_input(self.hass, user_input)
            except PhoneOrEmailFail as error:
                _LOGGER.exception(error)
                errors["base"] = "phone_email_invalid"
            except LoginError as error:
                _LOGGER.exception(error)
                errors["base"] = "pass_invalid"
            except Error as error:
                _LOGGER.exception(error)
                errors["base"] = "cannot_connect"

            if info:
                return self._advance_to_alias(user_input, info)

        return self.async_show_form(step_id="user_email", data_schema=vol.Schema(DATA_SCHEMA_EMAIL), errors=errors, last_step=False)

    @callback
    def _advance_to_alias(self, user_input: dict[str, Any], info: dict[str, str]) -> ConfigFlowResult:
        """Stash the validated credentials + display name, then move to the alias step."""
        self._account_data = user_input
        self._default_alias = info["username"]
        return self.async_show_form(
            step_id="alias",
            data_schema=self._alias_schema(self._default_alias),
            last_step=True,
        )

    @staticmethod
    def _alias_schema(default: str) -> vol.Schema:
        """Schema for the alias step: one required text field, pre-filled with ``default``."""
        return vol.Schema({vol.Required(CONF_ACCOUNT_ALIAS, default=default): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT))})

    async def async_step_alias(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Capture the user-chosen Account alias, then create the entry.

        The alias is the top of the account-token chain that differentiates the same watch when it
        is linked to several accounts (see helper.account_token; ref:XW-010). It is required and
        pre-filled with the Account display name, so a user who does not care can accept the
        default in one tap.
        """
        if user_input is not None:
            alias = user_input[CONF_ACCOUNT_ALIAS]
            data = {**self._account_data, CONF_ACCOUNT_ALIAS: alias}
            # Title the entry with the chosen alias so each account is distinguishable in the UI,
            # rather than every entry reading the manufacturer name.
            return self.async_create_entry(title=alias, data=data)

        return self.async_show_form(step_id="alias", data_schema=self._alias_schema(self._default_alias), last_step=True)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the Reconfigure flow: re-enter (or update) an existing entry's credentials.

        Reachable from Settings -> Devices & Services -> the entry's overflow menu, and pointed to by
        the `login_failed` repair issue this integration raises when the stored credentials stop
        working. It reuses the setup schema with the entry's current values *suggested*, so a user
        whose password changed (or who moves the account to a new e-mail/phone number) fixes it in
        place instead of deleting and re-adding the integration -- which would throw away every
        entity id, the recorder history behind it, and the accumulated location archive.

        The password is deliberately never pre-filled: it would be written back on submit even when
        untouched, and HA never sends secrets to the browser.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            merged = {**entry.data, **user_input}
            # Switching between phone and e-mail sign-in must not leave the other identifier
            # behind: `sign_in` keeps using whichever key is present, so a stale one would quietly
            # keep logging in with the old address.
            if user_input.get(CONF_PHONENUMBER):
                merged.pop(CONF_EMAIL, None)
            else:
                merged.pop(CONF_PHONENUMBER, None)

            info = None
            try:
                info = await validate_input(self.hass, merged)
            except PhoneOrEmailFail as error:
                _LOGGER.exception(error)
                errors["base"] = "phone_email_invalid"
            except LoginError as error:
                _LOGGER.exception(error)
                errors["base"] = "pass_invalid"
            except Error as error:
                _LOGGER.exception(error)
                errors["base"] = "cannot_connect"

            if info:
                unique_id = f"{merged.get(CONF_PHONENUMBER) or merged.get(CONF_EMAIL)}"
                # A changed identifier becomes a changed unique id; refuse to steal another
                # entry's id (HA dedupes/joins on it) instead of silently creating a collision.
                if unique_id != entry.unique_id and any(
                    other.unique_id == unique_id
                    for other in self._async_current_entries(include_ignore=True)
                    if other.entry_id != entry.entry_id
                ):
                    return self.async_abort(reason="already_configured")
                # `async_update_and_abort` writes the entry and lets the entry's update listener
                # (`__init__.options_update_listener`) schedule the reload, so no explicit reload.
                return self.async_update_and_abort(entry, unique_id=unique_id, data=merged, reason="reconfigure_successful")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(DATA_SCHEMA_PHONE if CONF_PHONENUMBER in entry.data else DATA_SCHEMA_EMAIL),
                {key: value for key, value in entry.data.items() if key != CONF_PASSWORD},
            ),
            errors=errors,
        )


def flatten_sections(user_input: dict[str, Any]) -> dict[str, Any]:
    """Merge a sectioned form's nested values back into one flat options dict.

    A form built with `data_entry_flow.section` submits its values **nested** under the section key
    (`{"polling": {"scan_interval": "1800"}}`), matching how core integrations consume them (e.g.
    `nzbget`: `more_options = user_input.pop(CONF_MORE_OPTIONS, {})`). Everything else in this
    integration -- the coordinator, the config registry, and every entry written by an older
    version -- reads a flat mapping of option key -> value, so the sections are unwrapped here, at
    the single point where the form's raw payload enters the integration.

    Unknown top-level keys are passed through unchanged, so a future non-sectioned field keeps
    working without touching this function.
    """
    flat: dict[str, Any] = {}
    for key, value in user_input.items():
        if key in OPTIONS_SECTIONS and isinstance(value, dict):
            flat.update(value)
        else:
            flat[key] = value
    return flat


class XploraOptionsFlowHandler(OptionsFlow):
    """Handle a option flow.

    Derives from HA's plain `OptionsFlow` rather than the phased-out `OptionsFlowWithConfigEntry`
    ("This class is being phased out, and should not be referenced in new code" -- core 2026.9.3):
    HA injects `self.config_entry` before the first step runs, so the handler takes no constructor
    argument and `async_get_options_flow` returns it bare.

    The form is grouped into collapsible **sections** (the core `data_entry_flow.section` pattern)
    so the ~17 settings read as six scannable groups instead of one long list. Two house rules come
    with sections, and both are handled here:

    * Values arrive **nested** under their section key
      (`{"polling": {"scan_interval": "1800"}}`) -- `flatten_sections` merges them back into the
      flat options dict the rest of the integration reads.
    * Translations move to `options.step.init.sections.<key>.{name,data,data_description}`; a flat
      `options.step.init.data` block is **never** consulted for a sectioned field, so the section
      keys below and `strings.json` must stay in lockstep.
    """

    @staticmethod
    def _option_labels(language: str, table: dict[str, dict[Any, str]]) -> list[SelectOptionDict]:
        """Localized `SelectOptionDict`s for a per-language label table (UI language, en fallback)."""
        return [SelectOptionDict(value=str(value), label=label) for value, label in table.get(language, table[DEFAULT_LANGUAGE]).items()]

    def get_options(
        self,
        signin_typ: list[str],
        watch_schema: OrderedDict[Any, Any],
        language: str,
        home_latitude: float,
        home_longitude: float,
        home_radius: int,
    ) -> vol.Schema:
        """Build the sectioned options schema (the flow's single source of truth)."""
        _options = self.config_entry.options

        general = vol.Schema(
            {
                vol.Required(CONF_SIGNIN_TYP, default=signin_typ[0]): SelectSelector(
                    SelectSelectorConfig(
                        options=[SelectOptionDict(value=signin, label=signin) for signin in signin_typ],
                        multiple=False,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Required(CONF_LANGUAGE, default=language): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=language_key, label=language_value)
                            for language_dict in SUPPORTED_LANGUAGES
                            for language_key, language_value in language_dict.items()
                        ],
                        multiple=False,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        polling = vol.Schema(
            {
                # The preset selector hands back the seconds as a string; the stored value is
                # canonicalized to an int in `async_step_init`.
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=str(normalize_scan_interval(_options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=self._option_labels(language, SCAN_INTERVAL_OPTIONS),
                        multiple=False,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_SCAN_INTERVAL_FUNCTIONS,
                    default=str(
                        normalize_scan_interval_functions(_options.get(CONF_SCAN_INTERVAL_FUNCTIONS, DEFAULT_SCAN_INTERVAL_FUNCTIONS))
                    ),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=self._option_labels(language, SCAN_INTERVAL_FUNCTIONS_OPTIONS),
                        multiple=False,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_REFRESH_ON_CARD_RENDER,
                    default=_options.get(CONF_REFRESH_ON_CARD_RENDER, DEFAULT_REFRESH_ON_CARD_RENDER),
                ): BooleanSelector(),
            }
        )

        location = vol.Schema(
            {
                vol.Required(CONF_HOME_SAFEZONE, default=_options.get(CONF_HOME_SAFEZONE, STATE_OFF)): SelectSelector(
                    SelectSelectorConfig(
                        options=self._option_labels(language, HOME_SAFEZONE),
                        multiple=False,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_HOME_LATITUDE, default=_options.get(CONF_HOME_LATITUDE, home_latitude)): cv.latitude,
                vol.Required(CONF_HOME_LONGITUDE, default=_options.get(CONF_HOME_LONGITUDE, home_longitude)): cv.longitude,
                vol.Required(CONF_HOME_RADIUS, default=_options.get(CONF_HOME_RADIUS, home_radius)): cv.positive_int,
                vol.Required(CONF_MAPS, default=_options.get(CONF_MAPS, MAPS[0])): SelectSelector(
                    SelectSelectorConfig(
                        options=[SelectOptionDict(value=value, label=value) for value in MAPS],
                        multiple=False,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_OPENCAGE_APIKEY, default=_options.get(CONF_OPENCAGE_APIKEY, "")): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
            }
        )

        history = vol.Schema(
            {
                vol.Required(
                    CONF_AUTO_FETCH_HISTORY,
                    default=_options.get(CONF_AUTO_FETCH_HISTORY, DEFAULT_AUTO_FETCH_HISTORY),
                ): BooleanSelector(),
                # How many days of location history to retain in the Store (the location-history
                # sensor is opt-in; this only matters once it is enabled). Lets HA keep far more
                # than the app's ~3-day window.
                vol.Required(
                    CONF_HISTORY_RETENTION_DAYS,
                    default=_options.get(CONF_HISTORY_RETENTION_DAYS, DEFAULT_HISTORY_RETENTION_DAYS),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=HISTORY_RETENTION_DAYS_MIN,
                        max=HISTORY_RETENTION_DAYS_MAX,
                        mode=NumberSelectorMode.SLIDER,
                    ),
                ),
            }
        )

        chat = vol.Schema(
            {
                vol.Required(CONF_MESSAGE, default=_options.get(CONF_MESSAGE, 10)): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=100,
                        mode=NumberSelectorMode.SLIDER,
                    ),
                ),
                vol.Required(CONF_REMOVE_MESSAGE, default=_options.get(CONF_REMOVE_MESSAGE, False)): BooleanSelector(),
                vol.Required(CONF_AUTO_MARK_READ, default=_options.get(CONF_AUTO_MARK_READ, False)): BooleanSelector(),
            }
        )

        notifications = vol.Schema(
            {
                # Per-category notification toggles (ADR 0016). SOS defaults ON (safety); calls/power/
                # low-battery default OFF. Enabling calls or SOS writes contact numbers/names + SOS GPS
                # to the recorder via the logbook line -- the PII warning is in the options strings.
                vol.Required(CONF_NOTIFY_SOS, default=_options.get(CONF_NOTIFY_SOS, True)): BooleanSelector(),
                vol.Required(CONF_NOTIFY_CALL, default=_options.get(CONF_NOTIFY_CALL, False)): BooleanSelector(),
                vol.Required(CONF_NOTIFY_POWER, default=_options.get(CONF_NOTIFY_POWER, False)): BooleanSelector(),
                vol.Required(CONF_NOTIFY_LOW_POWER, default=_options.get(CONF_NOTIFY_LOW_POWER, False)): BooleanSelector(),
            }
        )

        return vol.Schema(
            {
                # Watch selection + account alias lead: they are what a multi-account user has to
                # get right, and both apply to every watch. Everything else is grouped by the job
                # it does and collapsed, so the dialog opens short.
                vol.Required(SECTION_WATCHES): section(vol.Schema(dict(watch_schema)), SectionConfig(collapsed=False)),
                vol.Required(SECTION_POLLING): section(polling, SectionConfig(collapsed=False)),
                vol.Required(SECTION_LOCATION): section(location, SectionConfig(collapsed=True)),
                vol.Required(SECTION_CHAT): section(chat, SectionConfig(collapsed=True)),
                vol.Required(SECTION_NOTIFICATIONS): section(notifications, SectionConfig(collapsed=True)),
                vol.Required(SECTION_HISTORY): section(history, SectionConfig(collapsed=True)),
                vol.Required(SECTION_GENERAL): section(general, SectionConfig(collapsed=True)),
            }
        )

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle options flow."""
        errors: dict[str, str] = {}
        # Reuse the live coordinator's already-authenticated controller when the entry is loaded,
        # so opening the options screen doesn't trigger a fresh full login (and its retry churn)
        # against the rate-limit-sensitive auth endpoint every time. Fall back to a one-off login
        # only when no loaded coordinator exists (e.g. the entry failed to set up).
        coordinator = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        if coordinator is not None:
            # Reuse the live, authenticated controller (no fresh login -- ban-defense), but its
            # `self.watchs` is cached from first login and `_wuid` is pinned to the saved selection,
            # so `getWatchUserIDs()` would only ever echo the already-selected watches. Force one
            # fresh `deviceList` fetch so a watch added since setup is offered. Best-effort: a
            # transient failure must not lock the user out of editing unrelated options, so fall back
            # to the last-known list (still non-empty for a reused controller) on any client error.
            controller = coordinator.controller
            try:
                await controller.reload_watch_list()
            except (Error, RateLimitError, AuthError) as err:
                _LOGGER.debug("Could not refresh the watch list for the options screen: %s", err)
        else:
            # No loaded coordinator (e.g. the entry failed to set up): `sign_in` runs `init()`, which
            # already loads the current account list into a controller with no pinned `_wuid`, so no
            # extra reload is needed here.
            controller = await sign_in(hass=self.hass, data=self.config_entry.data)
        # Enumerate the full account (not the `_wuid`-pinned `getWatchUserIDs`, which stays the
        # entity-scoping filter); the saved `CONF_WATCHES` below keeps current picks pre-selected.
        watches = controller.getAllWatchUserIDs()
        _options = self.config_entry.options

        watch_schema: OrderedDict[Any, Any] = OrderedDict()
        watch_schema[vol.Required(CONF_WATCHES, default=_options.get(CONF_WATCHES, watches))] = SelectSelector(
            SelectSelectorConfig(
                options=[
                    # Keep the watch id as the stored value (it is matched against CONF_WATCHES
                    # throughout), but show the child's name in the list.
                    SelectOptionDict(
                        value=watch,
                        label=watch_user_label(controller, watch),
                    )
                    for watch in watches
                ],
                multiple=True,
                mode=SelectSelectorMode.LIST,
            )
        )
        # Editable Account alias (see helper.account_token; ref:XW-010). Pre-fill with the current
        # resolved alias; for a pre-alias entry that has none yet, fall back to the Account display
        # name so the field is never blank. The submitted value is stored in options, which
        # `resolve_account_alias` reads before data, so an edit here wins over the setup value and
        # the device name updates on the next load.
        watch_schema[vol.Required(CONF_ACCOUNT_ALIAS, default=resolve_account_alias(self.config_entry) or controller.getUserName())] = (
            TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT))
        )

        language: str = resolve_language(self.config_entry)

        signin_typ = [
            (
                SIGNIN.get(language, SIGNIN[DEFAULT_LANGUAGE])[CONF_EMAIL]
                if CONF_EMAIL in self.config_entry.data
                else SIGNIN.get(language, SIGNIN[DEFAULT_LANGUAGE])[CONF_PHONENUMBER]
            )
        ]

        # Home defaults for the location section. A missing (or renamed) `home` zone used to abort
        # the whole dialog with `HomeAssistantError("Zone 'home' not found")`, which locked the user
        # out of *every* setting -- polling, chat, alias -- because of one geography field. Fall
        # back to HA's own configured location (`hass.config`, set during onboarding and always
        # present) and the default zone radius instead, so the form always opens.
        home_state = self.hass.states.get(HOME)
        home_attrs = home_state.attributes if home_state is not None else {}
        if home_state is None:
            _LOGGER.debug("Zone '%s' not found; using Home Assistant's configured location as the home default", HOME)

        options = self.get_options(
            signin_typ,
            watch_schema,
            language,
            float(home_attrs.get(ATTR_LATITUDE, self.hass.config.latitude)),
            float(home_attrs.get(ATTR_LONGITUDE, self.hass.config.longitude)),
            int(home_attrs.get(CONF_RADIUS, DEFAULT_HOME_RADIUS)),
        )

        if user_input is not None:
            # Sectioned forms submit nested values; the integration reads a flat options dict.
            flat = flatten_sections(user_input)
            errors = validate_options_input(flat)

            if not errors:
                # The preset selector hands back the seconds as a string; store the canonical
                # int so the coordinator can use it directly (and stays consistent with the
                # legacy int-typed option).
                flat[CONF_SCAN_INTERVAL] = normalize_scan_interval(flat.get(CONF_SCAN_INTERVAL))
                flat[CONF_SCAN_INTERVAL_FUNCTIONS] = normalize_scan_interval_functions(flat.get(CONF_SCAN_INTERVAL_FUNCTIONS))
                # Store the canonical (clamped) int so the coordinator can use it directly.
                flat[CONF_HISTORY_RETENTION_DAYS] = normalize_history_retention_days(flat.get(CONF_HISTORY_RETENTION_DAYS))
                return self.async_create_entry(title="", data=flat)

        return self.async_show_form(step_id="init", data_schema=options, errors=errors)
