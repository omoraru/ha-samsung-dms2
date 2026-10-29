"""Client for the legacy Samsung DMS2 (2017 Silverlight firmware) web API.

The old DMS2 firmware drives a single endpoint, /dms2/dataCommunication, with
an XML-over-POST protocol. Authentication is a "secured form" login to
Login.jsp: the credentials are suffixed with the JSESSIONID and posted as
securedUsername / securedPassword (reverse-engineered from the shipped
Login.xap / dms2global.js — the RSA wrapping seen in the source was disabled in
firmware 2.7.0.6 in favour of plain concatenation over HTTPS).

Every request body is "<uuid>:<xml>"; responses come back the same way.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime

import aiohttp

_LOGGER = logging.getLogger(__name__)


class SamsungDMSError(Exception):
    """Base error."""


class SamsungDMSAuthError(SamsungDMSError):
    """Authentication failed."""


class SamsungDMSConnectionError(SamsungDMSError):
    """Could not talk to the DMS."""


def _envelope(payload: str) -> str:
    """Wrap a payload fragment in the DMS request envelope."""
    now = datetime.now()
    dt = f"{now.strftime('%Y-%m-%dT%H:%M:%S')}:{now.microsecond // 1000:03d}"
    return (
        "<?xml version=\"1.0\" encoding=\"utf-8\" standalone=\"yes\"?>"
        "<root xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" "
        "xsi:noNamespaceSchemaLocation=\"./xml/schema/login.xsd\">"
        "<header sa=\"web\" da=\"dms\" messageType=\"request\" "
        f"dateTime=\"{dt}\" dvmControlMode=\"individual\"/>"
        f"{payload}</root>"
    )


def _parse_response(text: str) -> ET.Element:
    """Strip the 'uuid:' prefix and parse the response XML to an Element."""
    _, _, body = text.partition(":")
    body = body.strip()
    if not body:
        raise SamsungDMSError("Empty response body")
    # Encode to bytes so ElementTree accepts the encoding declaration.
    return ET.fromstring(body.encode("utf-8"))


class SamsungDMSLegacyClient:
    """Minimal async client for the legacy DMS2 web API."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._host = host
        self._username = username
        self._password = password
        self._base = f"https://{host}/dms2"
        self._external_session = session is not None
        self._session = session
        # ssl=False on each request disables verification (self-signed cert)
        # without building an SSLContext in the event loop. The panel speaks
        # TLS 1.2, so no legacy-cipher handling is needed.
        self._lock = asyncio.Lock()
        self._authenticated = False
        # We manage JSESSIONID by hand: aiohttp's default cookie jar drops
        # cookies from IP-address hosts (unsafe=False), so the panel's session
        # cookie never gets stored otherwise.
        self._sid: str | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._external_session:
            await self._session.close()
            self._session = None

    def _capture_sid(self, resp: aiohttp.ClientResponse) -> None:
        """Pull JSESSIONID out of a response's Set-Cookie, if present."""
        morsel = resp.cookies.get("JSESSIONID")
        if morsel is not None and morsel.value:
            self._sid = morsel.value

    def _cookie_header(self) -> dict[str, str]:
        return {"Cookie": f"JSESSIONID={self._sid}"} if self._sid else {}

    async def login(self) -> None:
        """Perform the secured-form login and establish an authenticated session."""
        session = await self._get_session()
        try:
            # 1. Mint a JSESSIONID (read it from Set-Cookie ourselves).
            async with session.get(
                f"{self._base}/Login.jsp", ssl=False
            ) as resp:
                await resp.read()
                self._capture_sid(resp)

            if not self._sid:
                raise SamsungDMSConnectionError("No JSESSIONID cookie from DMS")

            # 2. Secured-form login: credential + session id, no encryption.
            data = {
                "securedUsername": f"{self._username}{self._sid}",
                "securedPassword": f"{self._password}{self._sid}",
            }
            async with session.post(
                f"{self._base}/Login.jsp",
                data=data,
                ssl=False,
                allow_redirects=False,
                headers=self._cookie_header(),
            ) as resp:
                body = await resp.text()
                self._capture_sid(resp)  # server may rotate the session id
                location = resp.headers.get("Location", "")
                if "loginError" in location or "loginError" in body:
                    raise SamsungDMSAuthError("DMS rejected the credentials")
        except aiohttp.ClientError as err:
            raise SamsungDMSConnectionError(str(err)) from err

        # 3. Verify by making a lightweight authenticated call.
        root = await self._call("<getSystemSummary/>", _skip_auth=True)
        if root is None:
            raise SamsungDMSAuthError("Login did not establish a session")
        self._authenticated = True

    async def _call(self, payload: str, _skip_auth: bool = False) -> ET.Element | None:
        """POST a payload to dataCommunication; return parsed root or None on redirect."""
        session = await self._get_session()
        body = f"{uuid.uuid4()}:{_envelope(payload)}"
        headers = {"Content-Type": "text/xml", **self._cookie_header()}
        try:
            async with session.post(
                f"{self._base}/dataCommunication",
                data=body.encode("utf-8"),
                headers=headers,
                ssl=False,
                allow_redirects=False,
            ) as resp:
                if resp.status in (301, 302, 303, 307, 308):
                    # Redirect to login => session not authenticated.
                    return None
                if resp.status != 200:
                    raise SamsungDMSConnectionError(f"HTTP {resp.status}")
                text = await resp.text()
                self._capture_sid(resp)
        except aiohttp.ClientError as err:
            raise SamsungDMSConnectionError(str(err)) from err

        root = _parse_response(text)
        header = root.find("header")
        if header is not None and header.get("messageType") == "exception":
            exc = root.find("exception")
            code = exc.get("code") if exc is not None else "?"
            desc = exc.get("description") if exc is not None else ""
            # An auth/session exception bubbles up as None so the caller re-logins.
            raise SamsungDMSError(f"DMS exception {code}: {desc}")
        return root

    async def _call_authed(self, payload: str) -> ET.Element:
        """Call with a single re-login retry on session loss."""
        async with self._lock:
            if not self._authenticated:
                await self.login()
            root = await self._call(payload)
            if root is None:
                # Session expired; re-login once.
                self._authenticated = False
                await self.login()
                root = await self._call(payload)
            if root is None:
                raise SamsungDMSAuthError("Not authenticated after re-login")
            return root

    async def async_get_monitoring(self) -> dict[str, dict]:
        """Return {addr: {attributes...}} for every indoor unit."""
        root = await self._call_authed("<getMonitoring><all/></getMonitoring>")
        result: dict[str, dict] = {}
        all_node = root.find("getMonitoring/all")
        if all_node is None:
            return result
        for indoor in all_node.findall("indoor"):
            addr = indoor.get("addr")
            detail = indoor.find("indoorDetail")
            if addr is None or detail is None:
                continue
            result[addr] = dict(detail.attrib)
        return result

    async def async_set_control(self, addr: str, values: dict[str, str]) -> None:
        """Send a control command to one indoor unit.

        `values` holds only the field(s) to change, e.g.
        {"power": "on"}, {"operationMode": "heat"}, {"setTemp": "23.0"},
        {"fanSpeed": "auto"}. Verified live against the panel 2026-10-28.
        """
        if not values:
            return
        inner = "".join(f"<{k}>{v}</{k}>" for k, v in values.items())
        payload = (
            "<setDeviceControl><controlList><control>"
            f"<controlValue>{inner}</controlValue>"
            f"<addressList><address>{addr}</address></addressList>"
            "</control></controlList></setDeviceControl>"
        )
        # _call_authed raises SamsungDMSError if the panel returns an exception.
        await self._call_authed(payload)

    async def async_get_errors(self) -> dict[str, dict]:
        """Return {addr: {code, desc, date}} for every active error.

        Pulled from getStatusUpload, which carries per-indoor `<error>` elements
        (e.g. an outdoor fault surfaced on its indoor units) plus the
        commErrorList. getMonitoring only exposes a boolean `error` flag.
        """
        root = await self._call_authed("<getStatusUpload>all</getStatusUpload>")
        out: dict[str, dict] = {}
        for err in root.iter("error"):
            addr = err.get("addr")
            if addr and err.get("errorStatus") == "true":
                out[addr] = {
                    "code": err.get("errorCode"),
                    "desc": err.get("errorDescription"),
                    "date": err.get("occurDate"),
                }
        return out

    async def async_get_names(self) -> dict[str, str]:
        """Return {addr: configured_name} for indoor units (skips '-'/blank)."""
        root = await self._call_authed("<getZoneInfo>all</getZoneInfo>")
        names: dict[str, str] = {}
        for dev in root.iter("device"):
            if dev.get("type") != "indoor":
                continue
            addr = dev.get("addr")
            name = (dev.get("name") or "").strip()
            if addr and name and name != "-":
                names[addr] = name
        return names

    async def async_get_zones(self) -> list[dict]:
        """Return a flat list of {addr, name, zone} for indoor devices (diagnostics)."""
        root = await self._call_authed("<getZoneInfo>all</getZoneInfo>")
        out: list[dict] = []
        current_zone = None
        for el in root.iter():
            if el.tag == "zone":
                current_zone = el.get("name")
            elif el.tag == "device" and el.get("type") == "indoor":
                out.append(
                    {
                        "addr": el.get("addr"),
                        "name": (el.get("name") or "").strip(),
                        "zone": current_zone,
                    }
                )
        return out
