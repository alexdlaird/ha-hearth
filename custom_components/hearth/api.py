__copyright__ = "Copyright (c) 2026 Alex Laird"
__license__ = "MIT"

import json
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from custom_components.hearth.const import (
    DEFAULT_RETRY_AFTER,
    PROTOCOL,
    READINGS_SOURCE,
    READINGS_SOURCE_NAME,
    REQUEST_TIMEOUT,
)
from custom_components.hearth.exception import (
    HearthAuthError,
    HearthConnectionError,
    HearthDemoHomeError,
    HearthRateLimitedError,
    HearthRejectedError,
)


@dataclass(frozen=True)
class ReadingsResult:
    """
    What Hearth said about a readings post.
    """

    #: The posted sensors that aren't added to a room in the Hearth app yet (Hearth drops their readings).
    not_added: list[str] = field(default_factory=list)


class HearthClient:
    """
    A connection to one Hearth home through its API key: ``/v1/bridge`` for the thermostat and ``/v1/readings`` for
    room sensors.
    """

    def __init__(self,
                 session: aiohttp.ClientSession,
                 api_key: str,
                 base_url: str) -> None:
        self._session = session
        self._api_key = api_key

        #: Where Hearth's API is (Hearth's own unless the integration is pointed at another backend).
        self.base_url: str = base_url.rstrip("/")

    async def async_check_key(self) -> None:
        """
        Check that Hearth takes the API key, with an empty readings post (which changes nothing).

        :raises: :class:`~custom_components.hearth.exception.HearthError`: When Hearth doesn't take the key or can't
            be reached.
        """
        await self._post("/v1/readings", {"source": READINGS_SOURCE, "sensors": []})

    async def async_sync_thermostat(self,
                                    thermostat: dict[str, Any],
                                    refused: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """
        Post the thermostat to Hearth.

        :param thermostat: The thermostat, as ``/v1/bridge`` takes it.
        :param refused: The last setting that couldn't be applied (as Hearth answered it), why, and who refused it.
        :return: The setting Hearth wants applied, if any.
        :raises: :class:`~custom_components.hearth.exception.HearthError`: When Hearth refuses the post or can't be
            reached.
        """
        payload: dict[str, Any] = {"protocol": PROTOCOL, "thermostat": thermostat}
        if refused is not None:
            payload["refused"] = refused
        status, body = await self._post("/v1/bridge", payload)
        desired = body.get("desired") if status == 200 and isinstance(body, dict) else None
        return desired if isinstance(desired, dict) else None

    async def async_post_readings(self, sensors: list[dict[str, Any]]) -> ReadingsResult:
        """
        Post room sensors' readings to Hearth, which keeps only those of sensors added in its app.

        :param sensors: The readings, as ``/v1/readings`` takes them.
        :return: What Hearth said about them.
        :raises: :class:`~custom_components.hearth.exception.HearthError`: When Hearth refuses the post or can't be
            reached.
        """
        status, body = await self._post("/v1/readings", {
            "source": READINGS_SOURCE,
            "name": READINGS_SOURCE_NAME,
            "sensors": sensors
        })
        if status == 422:
            return ReadingsResult([str(sensor["id"]) for sensor in sensors])
        not_added = body.get("not_added") if isinstance(body, dict) else None
        return ReadingsResult([str(name) for name in not_added] if isinstance(not_added, list) else [])

    async def _post(self, path: str, payload: dict[str, Any]) -> tuple[int, Any]:
        try:
            async with self._session.post(f"{self.base_url}{path}",
                                          json=payload,
                                          headers={"Authorization": f"Bearer {self._api_key}"},
                                          timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as response:
                text = await response.text()
                status = response.status
                retry_after = response.headers.get("Retry-After")
        except (aiohttp.ClientError, TimeoutError) as e:
            raise HearthConnectionError(f"Couldn't reach Hearth: {e}") from e

        if status in (200, 204, 422):
            return status, _json(text) if text else None
        elif status == 401:
            raise HearthAuthError("Hearth didn't accept the API key.")
        elif status == 403:
            raise HearthDemoHomeError(text or "The API key belongs to a demo home.")
        elif status == 429:
            raise HearthRateLimitedError("Hearth asked for fewer posts.", {"retry_after": _seconds(retry_after)})
        elif status >= 500:
            raise HearthConnectionError(f"Hearth answered {status}.")
        else:
            raise HearthRejectedError(text[:300] or f"Hearth answered {status}.")


def _json(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return None


def _seconds(value: str | None) -> int:
    try:
        return max(1, int(value)) if value is not None else DEFAULT_RETRY_AFTER
    except ValueError:
        return DEFAULT_RETRY_AFTER
