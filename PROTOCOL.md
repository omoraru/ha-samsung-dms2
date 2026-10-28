# Samsung DMS2 (2017 Silverlight firmware) — local API protocol

Reverse-engineered from a `MIM-B18` DMS2.5 panel running the 2017 Silverlight
firmware, by decompiling the shipped `Login.xap` and `DMS_Client.dll` and
reading `dms2global.js`, then confirming reads and a control write against live
hardware. This is what `samsung_dms_legacy` implements.

## Transport

- Base: `https://<host>/dms2/` — self-signed cert (verification off). The panels
  tested speak TLS 1.2.
- One data endpoint after login: **`POST /dms2/dataCommunication`**,
  `Content-Type: text/xml`.
- Request **body** = `"<uuid>:<xml>"` — a fresh GUID, a colon, then the XML.
- Response body = `"<uuid>:<xml>"` too — strip up to the first `:` then parse
  (parse as **bytes**; the XML declares `encoding='UTF-8'`).
- **Session cookie must be handled manually.** Many HTTP clients (including
  aiohttp's default cookie jar) drop cookies from IP-address hosts, so read
  `JSESSIONID` from the `Set-Cookie` header yourself and send it back.

## Request envelope

```xml
<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:noNamespaceSchemaLocation="./xml/schema/login.xsd">
  <header sa="web" da="dms" messageType="request"
          dateTime="YYYY-MM-DDTHH:MM:SS:mmm" dvmControlMode="individual"/>
  <!-- payload fragment -->
</root>
```

`dateTime` is the .NET sortable format (`ToString("s")`) plus `:` plus the
millisecond as three digits.

## Authentication — "secured form" login

The admin login is **not** the XML `<login>` payload (that path is guest-only;
posting it to `dataCommunication` redirects to `/dms2/main/loginError.jsp`).
The real flow (`_btnLogin_Click` → JS `setAccount` → `submitEncryptedForm`):

1. `GET /dms2/Login.jsp` → sets a `JSESSIONID` cookie.
2. `POST /dms2/Login.jsp` (form-urlencoded, same cookie) with:
   - `securedUsername = <username> + <JSESSIONID>`
   - `securedPassword = <password> + <JSESSIONID>`

   The RSA wrapping present in the source was disabled in firmware 2.7.0.6 once
   the panels served HTTPS — it is now plain concatenation.
3. Success → the session cookie is authenticated; failure → redirect to
   `loginError.jsp`.

Verify auth with any data call: the response `header/@messageType` is `response`
(not `exception`) and the status is not a 3xx redirect.

The login form itself is simply:

```html
<form id="securedLoginForm" action="Login.jsp" method="post">
  <input type="hidden" name="securedUsername" />
  <input type="hidden" name="securedPassword" />
</form>
```

## Read payloads

| Purpose             | Payload fragment                        |
|---------------------|-----------------------------------------|
| All unit state      | `<getMonitoring><all/></getMonitoring>` |
| Device tree + names | `<getZoneInfo>all</getZoneInfo>`        |
| System summary      | `<getSystemSummary/>`                    |
| Device/energy sum.  | `<getDeviceSummary/>`                    |

Not accepted on the tested firmware: `<treeInfo>all</treeInfo>` (`BA02 Wrong XML
attribute`), `<treeInfoEx><range>all</range></treeInfoEx>` (`NOPARAM`). Use
`getZoneInfo` for names.

### getMonitoring response

```xml
<getMonitoring><all>
  <indoor addr='11.00.00'>
    <indoorDetail power='off|on' opMode='auto|heat|cool|dry|fan'
      setTemp='24.0' roomTemp='22.1' fanSpeed='auto|low|mid|high'
      tempInterval='1' upperTemperature='30.0' lowerTemperature='18.0'
      useHeatMode='true' useCoolMode='true' error='false'
      filterWarning='false' remoconEnable='true' isScheduled='false'
      defrostOn='false' temperatureScale='Celsius' .../>
  </indoor>
  ...
</all></getMonitoring>
```

`-1000` / `null` = no value (typically a unit behind a faulted outdoor unit).

### getZoneInfo response (names + grouping)

```xml
<getZoneInfo><rootZone>
  <zone id='...' name='System 1'><properties zonetype='general'/>
    <device addr='11.00.01' name='Room label' type='indoor' .../>
    ...
```

`name='-'` or blank = unnamed. `type` is also `DI` / `DO` for digital I/O.

## Control — `setDeviceControl`

Include only the field(s) you want to change inside `<controlValue>`:

```xml
<setDeviceControl><controlList><control>
  <controlValue>
    <power>on|off</power>
    <operationMode>auto|heat|cool|dry|fan</operationMode>
    <setTemp>23.0</setTemp>
    <fanSpeed>auto|low|mid|high</fanSpeed>
  </controlValue>
  <addressList><address>11.00.00</address></addressList>
</control></controlList></setDeviceControl>
```

Multiple `<address>` entries apply one command to several units at once. A
successful write echoes the `controlValue` back in a `response`; a malformed one
returns an `exception` with a `code`. Observed: a `setTemp` write is accepted
even while the unit is powered off.

## Addressing

Addresses look like `<bus>.<outdoor>.<indoor>` (e.g. `11.00.03`). Digital I/O
devices use the `56.00.*` (inputs) / `56.01.*` (outputs) range on the tested
hardware.
