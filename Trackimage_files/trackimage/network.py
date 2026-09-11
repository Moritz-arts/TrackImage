"""The LAN switch, sessions, rate limiting and the QR code.

Layer 16 of 27 -- see trackimage/__init__.py for the order these load in.
"""
from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory, g, make_response, Response
)
import hashlib
import json
import os
import subprocess
import threading
import time as _time
from . import state
from .config import NET_DEFAULT_PW, _NET_LOCK_PAGE, _NET_SESSION_TTL, _VPN_HINTS, app
from .logging_setup import log
from .platform_bits import _no_window
from .appconfig import _app_config_load, _app_config_save


state._NET_ON = False             # is the port open to the LAN right now?


state._BIND_HOST = "127.0.0.1"    # localhost unless sharing is switched on


_HTTPD = {"srv": None, "thread": None, "host": ""}


_HTTPD_LOCK = threading.Lock()


def _serve_on(host, port=5001):
    """v4.32: (re)bind the web server to `host` while TrackImage keeps running.

    app.run() decides its address once and holds it until the process ends, which
    is why switching sharing on used to need a restart. werkzeug's make_server is
    the same server underneath but hands back an object that can be shut down, so
    the socket can be swapped while everything above it -- the database, the
    watcher, the tagger, the open window -- carries on untouched.

    0.0.0.0 already covers 127.0.0.1, so there is only ever one server."""
    from werkzeug.serving import make_server
    with _HTTPD_LOCK:
        if _HTTPD["srv"] is not None and _HTTPD["host"] == host:
            return True
        old = _HTTPD["srv"]
        # The old socket has to go first: 0.0.0.0 and 127.0.0.1 are the same port
        # and the second bind is refused while the first still holds it. That
        # leaves a fraction of a second with nothing listening -- a browser simply
        # retries, and the alternative is asking the user to restart.
        if old is not None:
            try:
                old.shutdown()          # asks serve_forever to return
            except Exception:
                pass
            ot = _HTTPD.get("thread")
            if ot is not None and ot.is_alive():
                ot.join(timeout=5)      # ...and it must actually have returned
            try:
                old.server_close()      # only now is the socket really released
            except Exception:
                pass

        # Even after server_close the port can need a moment: the old socket may
        # still be draining, and 0.0.0.0 and 127.0.0.1 are the same port. Without
        # this retry, toggling sharing off right after switching it on left
        # TrackImage with no server at all.
        srv, err = None, None
        for _attempt in range(10):
            try:
                srv = make_server(host, port, app, threaded=True)
                break
            except OSError as e:
                err = e
                _time.sleep(0.25)
        if srv is None:
            e = err or OSError("could not bind")
            log("Could not open the port on %s: %s" % (host, e), "error")
            # Put back what was working rather than leaving the app unreachable.
            if old is not None:
                try:
                    back = make_server(_HTTPD["host"] or "127.0.0.1", port, app, threaded=True)
                    bt = threading.Thread(target=back.serve_forever, daemon=True, name="http")
                    bt.start()
                    _HTTPD.update({"srv": back, "thread": bt})
                    log("Kept the previous address (%s)" % (_HTTPD["host"] or "127.0.0.1"))
                except Exception:
                    _HTTPD.update({"srv": None, "thread": None, "host": ""})
                    log("The web server could not be restarted \u2014 please restart "
                        "TrackImage", "error")
            return False
        t = threading.Thread(target=srv.serve_forever, daemon=True, name="http")
        t.start()
        _HTTPD.update({"srv": srv, "thread": t, "host": host})
        state._BIND_HOST = host
        state._NET_ON = (host == "0.0.0.0")
        return True


def _apply_network_state(enabled):
    """Open or close the port to the network, now, without a restart."""
    want = "0.0.0.0" if enabled else "127.0.0.1"
    if _HTTPD["host"] == want:
        return True
    ok = _serve_on(want)
    if ok:
        if enabled:
            ips = _lan_ips()
            log("Network sharing is ON \u2014 reachable at %s"
                % (", ".join("http://%s:5001" % i for i in ips) or "this computer's address"))
        else:
            _NET_SESSIONS.clear()      # the door is shut; no session outlives it
            log("Network sharing is OFF \u2014 TrackImage is local again")
    return ok


_NET_SESSIONS = {}          # token -> last-seen timestamp


_NET_FAILS = {}             # remote address -> [count, first-attempt time]


def _net_cfg():
    c = _app_config_load()
    return {"enabled": bool(c.get("network_enabled", False)),
            "password": str(c.get("network_password", NET_DEFAULT_PW) or NET_DEFAULT_PW),
            "port": int(c.get("network_port", 5001) or 5001)}


def _net_cfg_save(**kw):
    c = _app_config_load()
    c.update(kw)
    _app_config_save(c)


_NET_REACHED = {"host": "", "ts": 0.0}      # an address a device really connected on


def _adapter_info():
    """v4.32: {ipv4: {"name","physical","virtual"}} on Windows, without reading a
    word of localised text.

    The previous version parsed `netsh` output for the strings "configuration for
    interface" and "ip address:". On a German Windows those read "Konfiguration
    fuer Schnittstelle" and "IP-Adresse:", so the parser matched nothing, every
    adapter stayed unclassified, and a VPN tunnel was offered as the address to
    type into a phone. Parsing a localised UI was the mistake; PowerShell returns
    structured objects whose property names are English on every install, and
    Get-NetAdapter states outright whether an adapter is virtual."""
    out = {}
    if os.name != "nt":
        return out
    ps = ("$ErrorActionPreference='SilentlyContinue';"
          "$a=Get-NetAdapter | Select-Object Name,ifIndex,Virtual,PhysicalMediaType,"
          "InterfaceDescription;"
          "$i=Get-NetIPAddress -AddressFamily IPv4 | Select-Object IPAddress,InterfaceIndex;"
          "ConvertTo-Json -Compress -Depth 4 @{adapters=@($a);addresses=@($i)}")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                            "-ExecutionPolicy", "Bypass", "-Command", ps],
                           **_no_window({"capture_output": True, "text": True, "timeout": 20}))
        data = json.loads((r.stdout or "").strip())
        by_idx = {}
        for a in (data.get("adapters") or []):
            by_idx[a.get("ifIndex")] = {
                "name": a.get("Name") or "",
                "desc": a.get("InterfaceDescription") or "",
                "media": a.get("PhysicalMediaType") or "",
                "virtual": bool(a.get("Virtual")),
            }
        for e in (data.get("addresses") or []):
            ip = e.get("IPAddress") or ""
            ad = by_idx.get(e.get("InterfaceIndex"))
            if not ip or ip.startswith("127.") or not ad:
                continue
            media = (ad["media"] or "").lower()
            out[ip] = {
                "name": ad["name"] or ad["desc"],
                # 802.3 is Ethernet, "native 802.11" is Wi-Fi -- a real card on a
                # real network. Everything else is a tunnel, a bridge or a guess.
                "physical": ("802.3" in media or "802.11" in media) and not ad["virtual"],
                "virtual": ad["virtual"],
            }
        if out:
            return out
    except Exception:
        pass
    return _adapter_info_ctypes()


def _adapter_info_ctypes():
    """Fallback when PowerShell is unavailable or restricted: ask Windows
    directly. IF_TYPE values are numbers, so nothing here is translated either."""
    out = {}
    if os.name != "nt":
        return out
    try:
        import ctypes
        from ctypes import wintypes
        ETHERNET, WIFI, PPP, TUNNEL, LOOPBACK = 6, 71, 23, 131, 24

        class SOCKADDR(ctypes.Structure):
            _fields_ = [("sa_family", wintypes.USHORT), ("sa_data", ctypes.c_ubyte * 26)]

        class SOCKET_ADDRESS(ctypes.Structure):
            _fields_ = [("lpSockaddr", ctypes.POINTER(SOCKADDR)), ("iSockaddrLength", ctypes.c_int)]

        class IP_ADAPTER_UNICAST_ADDRESS(ctypes.Structure):
            pass
        IP_ADAPTER_UNICAST_ADDRESS._fields_ = [
            ("Length", wintypes.ULONG), ("Flags", wintypes.DWORD),
            ("Next", ctypes.POINTER(IP_ADAPTER_UNICAST_ADDRESS)),
            ("Address", SOCKET_ADDRESS), ("PrefixOrigin", ctypes.c_int),
            ("SuffixOrigin", ctypes.c_int), ("DadState", ctypes.c_int),
            ("ValidLifetime", wintypes.ULONG), ("PreferredLifetime", wintypes.ULONG),
            ("LeaseLifetime", wintypes.ULONG), ("OnLinkPrefixLength", ctypes.c_ubyte)]

        class IP_ADAPTER_ADDRESSES(ctypes.Structure):
            pass
        IP_ADAPTER_ADDRESSES._fields_ = [
            ("Length", wintypes.ULONG), ("IfIndex", wintypes.DWORD),
            ("Next", ctypes.POINTER(IP_ADAPTER_ADDRESSES)),
            ("AdapterName", ctypes.c_char_p),
            ("FirstUnicastAddress", ctypes.POINTER(IP_ADAPTER_UNICAST_ADDRESS)),
            ("FirstAnycastAddress", ctypes.c_void_p), ("FirstMulticastAddress", ctypes.c_void_p),
            ("FirstDnsServerAddress", ctypes.c_void_p), ("DnsSuffix", ctypes.c_wchar_p),
            ("Description", ctypes.c_wchar_p), ("FriendlyName", ctypes.c_wchar_p),
            ("PhysicalAddress", ctypes.c_ubyte * 8), ("PhysicalAddressLength", wintypes.DWORD),
            ("Flags", wintypes.DWORD), ("Mtu", wintypes.DWORD), ("IfType", wintypes.DWORD),
            ("OperStatus", ctypes.c_int)]

        size = wintypes.ULONG(15000)
        buf = ctypes.create_string_buffer(size.value)
        ret = ctypes.windll.iphlpapi.GetAdaptersAddresses(
            2, 0x0010 | 0x0020 | 0x0040, None, ctypes.cast(buf, ctypes.POINTER(IP_ADAPTER_ADDRESSES)),
            ctypes.byref(size))
        if ret == 111:                                  # ERROR_BUFFER_OVERFLOW
            buf = ctypes.create_string_buffer(size.value)
            ret = ctypes.windll.iphlpapi.GetAdaptersAddresses(
                2, 0x0010 | 0x0020 | 0x0040, None,
                ctypes.cast(buf, ctypes.POINTER(IP_ADAPTER_ADDRESSES)), ctypes.byref(size))
        if ret != 0:
            return out
        node = ctypes.cast(buf, ctypes.POINTER(IP_ADAPTER_ADDRESSES))
        while node:
            a = node.contents
            ua = a.FirstUnicastAddress
            while ua:
                sa = ua.contents.Address.lpSockaddr.contents
                if sa.sa_family == 2:                   # AF_INET
                    ip = ".".join(str(b) for b in sa.sa_data[2:6])
                    if not ip.startswith("127."):
                        out[ip] = {"name": a.FriendlyName or a.Description or "",
                                   "physical": a.IfType in (ETHERNET, WIFI),
                                   "virtual": a.IfType in (PPP, TUNNEL, LOOPBACK)}
                ua = ua.contents.Next
            node = a.Next
    except Exception:
        pass
    return out


def _adapter_map():
    """Backwards-compatible {ip: name} view of _adapter_info()."""
    return {ip: d["name"] for ip, d in _adapter_info().items()}


def _all_ipv4():
    out = []
    try:
        import socket as _s
        for fam, _t, _p, _c, sa in _s.getaddrinfo(_s.gethostname(), None):
            ip = sa[0]
            if fam == _s.AF_INET and not ip.startswith("127.") and ip not in out:
                out.append(ip)
    except Exception:
        pass
    if not out:
        try:
            import socket as _s
            sk = _s.socket(_s.AF_INET, _s.SOCK_DGRAM)
            try:
                sk.connect(("10.255.255.255", 1))   # route lookup, sends nothing
                out.append(sk.getsockname()[0])
            finally:
                sk.close()
        except Exception:
            pass
    return out


def _lan_ips():
    """The address(es) another device on this network can actually reach, best
    first. Evidence beats inference: an address a device has genuinely connected
    on wins over anything derived from adapter properties."""
    ips = _all_ipv4()
    info = _adapter_info()

    def rank(ip):
        d = info.get(ip)
        if d:
            if d["physical"]:
                return 0                        # Ethernet or Wi-Fi: a real network
            if d["virtual"]:
                return 3                        # tunnel, bridge, loopback
            return 2                            # known adapter, unclear type
        name = ""
        return 1 if not any(h in name for h in _VPN_HINTS) else 3

    physical = [ip for ip in ips if info.get(ip, {}).get("physical")]
    if physical:
        ordered = sorted(physical, key=lambda i: ips.index(i))
    else:
        # Nothing could be classified -- keep every address rather than filter on
        # a guess. Losing the right one is worse than showing one extra.
        ordered = sorted(ips, key=lambda i: (rank(i), ips.index(i)))
        ordered = [i for i in ordered if rank(i) < 3] or ordered
    seen = _NET_REACHED.get("host")
    if seen and seen in ips:
        ordered = [seen] + [i for i in ordered if i != seen]
    return ordered


def _lan_ips_detail():
    """Every address with what is known about it, for the settings page."""
    info = _adapter_info()
    best = (_lan_ips() or [""])[0]
    out = []
    for ip in _all_ipv4():
        d = info.get(ip, {})
        name = d.get("name", "")
        out.append({"ip": ip, "adapter": name,
                    "physical": bool(d.get("physical")),
                    "tunnel": bool(d.get("virtual")) or
                              any(h in name.lower() for h in _VPN_HINTS),
                    "confirmed": ip == _NET_REACHED.get("host"),
                    "best": ip == best})
    return out


def _has_qrcode():
    try:
        import qrcode  # noqa: F401
        return True
    except Exception:
        return False


def _net_note_reached():
    """Record the address this request arrived on. A device that is talking to us
    proves that address works, which no amount of adapter inspection can."""
    try:
        h = (request.host or "").rsplit(":", 1)[0].strip("[]")
        if h and not h.startswith("127.") and h != "localhost":
            _NET_REACHED.update({"host": h, "ts": _time.time()})
    except Exception:
        pass


def _net_token_new():
    t = hashlib.sha256(os.urandom(32)).hexdigest()
    _NET_SESSIONS[t] = _time.time()
    return t


def _net_token_ok(t):
    if not t:
        return False
    seen = _NET_SESSIONS.get(t)
    if not seen:
        return False
    if _time.time() - seen > _NET_SESSION_TTL:
        _NET_SESSIONS.pop(t, None)
        return False
    _NET_SESSIONS[t] = _time.time()
    return True


def _is_local_request():
    """Requests from this machine are never challenged -- the window itself is a
    client, and locking the user out of their own app would be absurd."""
    try:
        ra = request.remote_addr or ""
        return ra in ("127.0.0.1", "::1", "localhost")
    except Exception:
        return True


def _net_rate_limited(addr):
    """Ten wrong guesses buys a five minute pause. A four digit default password
    is only reasonable if it cannot be walked through in seconds."""
    rec = _NET_FAILS.get(addr)
    if not rec:
        return False
    n, first = rec
    if _time.time() - first > 300:
        _NET_FAILS.pop(addr, None)
        return False
    return n >= 10


def _net_note_fail(addr):
    n, first = _NET_FAILS.get(addr, (0, _time.time()))
    _NET_FAILS[addr] = (n + 1, first)


@app.before_request
def _net_gate():
    """v4.30: every remote request must carry a valid session token.

    Local requests pass untouched. Remote ones get the unlock page instead of the
    app until they have entered the password -- and that applies to the API as
    much as the interface, since deleting a folder is an API call, not a click."""
    if not state._NET_ON or _is_local_request():
        return None
    path = request.path or ""
    # Only the two icon files are served before unlocking. v4.32 exempted all of
    # /static/, which was harmless while it held fonts -- but index.html lives
    # there since v4.33, and that would have handed the whole interface to any
    # device on the network without a password.
    if path.startswith("/api/net/unlock") or path in (
            "/static/trackimage.ico", "/static/trackimage.png", "/favicon.ico"):
        return None
    if _net_token_ok(request.cookies.get("ti_net")):
        _net_note_reached()
        return None
    if path.startswith("/api/"):
        return jsonify({"error": "locked", "locked": True}), 401
    return app.response_class(_NET_LOCK_PAGE, mimetype="text/html", status=401)
