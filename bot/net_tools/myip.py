from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple
import re

import dns.resolver
import dns.exception
import dns.rdataclass

OPENDNS_NS = ["208.67.222.222", "208.67.220.220"]  # resolver1/2.opendns.com
CLOUDFLARE_NS = ["1.1.1.1", "1.0.0.1"]
GOOGLE_AUTH_NS = ["216.239.32.10", "216.239.34.10", "216.239.36.10", "216.239.38.10"]  # ns1..ns4.google.com

_ipv4_re = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

@dataclass
class MyIpResult:
    ok: bool
    ip: Optional[str] = None
    source: Optional[str] = None
    resolver: Optional[str] = None
    error: Optional[str] = None


def _mk_resolver(servers: list[str], timeout: float) -> dns.resolver.Resolver:
    res = dns.resolver.Resolver(configure=False)
    res.lifetime = timeout
    res.timeout = timeout
    res.nameservers = servers
    return res

def _first_ipv4_from_txt(answer) -> Optional[str]:
    try:
        for r in answer:
            # dnspython >=2.x: r.to_text() -> '"text..."'
            txt = r.to_text().strip('"')
            m = _ipv4_re.search(txt)
            if m:
                return m.group(0)
    except Exception:
        pass
    return None


def _try_opendns(timeout: float) -> MyIpResult:
    res = _mk_resolver(OPENDNS_NS, timeout)
    try:
        ans = res.resolve("myip.opendns.com", "A", lifetime=timeout)
        ip = ans[0].to_text()
        return MyIpResult(ok=True, ip=ip, source="OpenDNS", resolver=",".join(res.nameservers))
    except dns.resolver.NXDOMAIN:
        return MyIpResult(ok=False, error="OpenDNS: NXDOMAIN")
    except dns.resolver.NoAnswer:
        return MyIpResult(ok=False, error="OpenDNS: No answer")
    except dns.resolver.Timeout:
        return MyIpResult(ok=False, error="OpenDNS: Timeout")
    except dns.exception.DNSException as e:
        return MyIpResult(ok=False, error=f"OpenDNS: DNS error: {e}")
    except Exception as e:
        return MyIpResult(ok=False, error=f"OpenDNS: Unexpected error: {e}")

def _try_cloudflare(timeout: float) -> MyIpResult:
    res = _mk_resolver(CLOUDFLARE_NS, timeout)
    try:
        # CH/TXT: whoami.cloudflare → содержит наш IP
        ans = res.resolve("whoami.cloudflare", "TXT", rdclass=dns.rdataclass.CH, lifetime=timeout)
        ip = _first_ipv4_from_txt(ans)
        if ip:
            return MyIpResult(ok=True, ip=ip, source="Cloudflare (CHAOS)", resolver=",".join(res.nameservers))
        return MyIpResult(ok=False, error="Cloudflare: TXT has no IP")
    except dns.resolver.NXDOMAIN:
        return MyIpResult(ok=False, error="Cloudflare: NXDOMAIN")
    except dns.resolver.NoAnswer:
        return MyIpResult(ok=False, error="Cloudflare: No answer")
    except dns.resolver.Timeout:
        return MyIpResult(ok=False, error="Cloudflare: Timeout")
    except dns.exception.DNSException as e:
        return MyIpResult(ok=False, error=f"Cloudflare: DNS error: {e}")
    except Exception as e:
        return MyIpResult(ok=False, error=f"Cloudflare: Unexpected error: {e}")

def _try_google(timeout: float) -> MyIpResult:
    res = _mk_resolver(GOOGLE_AUTH_NS, timeout)
    try:
        ans = res.resolve("o-o.myaddr.l.google.com", "TXT", lifetime=timeout)
        ip = _first_ipv4_from_txt(ans)
        if ip:
            return MyIpResult(ok=True, ip=ip, source="Google (TXT)", resolver=",".join(res.nameservers))
        return MyIpResult(ok=False, error="Google: TXT has no IP")
    except dns.resolver.NXDOMAIN:
        return MyIpResult(ok=False, error="Google: NXDOMAIN")
    except dns.resolver.NoAnswer:
        return MyIpResult(ok=False, error="Google: No answer")
    except dns.resolver.Timeout:
        return MyIpResult(ok=False, error="Google: Timeout")
    except dns.exception.DNSException as e:
        return MyIpResult(ok=False, error=f"Google: DNS error: {e}")
    except Exception as e:
        return MyIpResult(ok=False, error=f"Google: Unexpected error: {e}")


def lookup_v4(timeout: float = 4.0) -> MyIpResult:
    """
    Пытается определить внешний IPv4-адрес бота каскадом:
      1) OpenDNS A myip.opendns.com
      2) Cloudflare TXT (CHAOS) whoami.cloudflare
      3) Google TXT o-o.myaddr.l.google.com
    Возвращает первый успешный результат, иначе объединяет причины ошибок.
    """
    errs: list[str] = []

    r1 = _try_opendns(timeout)
    if r1.ok:
        return r1
    errs.append(r1.error or "OpenDNS: unknown")

    r2 = _try_cloudflare(timeout)
    if r2.ok:
        return r2
    errs.append(r2.error or "Cloudflare: unknown")

    r3 = _try_google(timeout)
    if r3.ok:
        return r3
    errs.append(r3.error or "Google: unknown")

    return MyIpResult(ok=False, error="; ".join(errs))