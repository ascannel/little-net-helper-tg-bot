from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Literal
import json
import datetime as dt
import re
import ipaddress

import whois as domain_whois
from ipwhois import IPWhois


@dataclass
class WhoisResult:
    ok: bool
    kind: Literal["domain", "ip"]
    target: str
    summary_lines: List[str]
    raw_text: Optional[str] = None
    error: Optional[str] = None


def _norm_date(v) -> str | None:
    # python-whois может возвращать list[datetime] либо одну datetime/str
    if isinstance(v, list) and v:
        v = v[0]
    if isinstance(v, dt.datetime):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, str):
        return v[:10]
    return None


def _join_ns(v) -> str | None:
    if isinstance(v, (list, tuple, set)):
        return ", ".join(sorted(map(str, v)))
    if isinstance(v, str):
        return v
    return None


# ---- NEW: фильтр «воды» из сырого WHOIS (ICANN/VeriSign notices, terms, last update и т.д.)
def _clean_whois_text(t: str | None) -> str | None:
    if not t:
        return t
    # Блочные уведомления (многострочные) — вырезаем до пустой строки/конца
    block_patterns = [
        r'^\s*NOTICE:.*?(?=^\s*$|\Z)',
        r'^\s*TERMS OF USE:.*?(?=^\s*$|\Z)',
        r'^\s*By submitting a WHOIS query.*?(?=^\s*$|\Z)',
        r'^\s*For more information on Whois status codes.*?(?=^\s*$|\Z)',
    ]
    for p in block_patterns:
        t = re.sub(p, "", t, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)

    # Разовые строки
    line_patterns = [
        r'^\s*>>> Last update of whois database:.*$',
        r'^\s*The Registry database contains ONLY.*$',
    ]
    for p in line_patterns:
        t = re.sub(p, "", t, flags=re.IGNORECASE | re.MULTILINE)

    # Убираем «лишние» пустые строки
    t = re.sub(r'\n{3,}', '\n\n', t, flags=re.MULTILINE).strip()
    return t

def lookup(target: str, timeout: float = 8.0) -> WhoisResult:
    t = (target or "").strip()
    # IP (IPv4 public) → RDAP через ipwhois
    try:
        ip = ipaddress.ip_address(t)
        if ip.version == 4 and (not ip.is_private and not ip.is_loopback and not ip.is_link_local and not ip.is_multicast and not ip.is_reserved):
            return _lookup_ip(str(ip), timeout)
        else:
            # IPv6/приватные/прочее тут не поддерживаем
            return WhoisResult(False, "ip", t, [], error="Поддерживается только публичный IPv4 (не приватный/loopback/link-local)")
    except ValueError:
        pass

    # Домены -> python-whois
    return _lookup_domain(t)


def _lookup_domain(domain: str) -> WhoisResult:
    try:
        w = domain_whois.whois(domain)
    except Exception as e:
        return WhoisResult(False, "domain", domain, [], error=f"WHOIS error: {e}")

    # Пытаемся собрать краткое резюме
    dn = (w.get("domain_name") if isinstance(w, dict) else getattr(w, "domain_name", None))
    if isinstance(dn, list):
        dn = dn[0]
    registrar = (w.get("registrar") if isinstance(w, dict) else getattr(w, "registrar", None))
    created = _norm_date(w.get("creation_date") if isinstance(w, dict) else getattr(w, "creation_date", None))
    expires = _norm_date(w.get("expiration_date") if isinstance(w, dict) else getattr(w, "expiration_date", None))
    ns = _join_ns(w.get("name_servers") if isinstance(w, dict) else getattr(w, "name_servers", None))
    status = w.get("status") if isinstance(w, dict) else getattr(w, "status", None)
    if isinstance(status, (list, tuple, set)):
        status = ", ".join(map(str, status))

    lines = []
    if dn: lines.append(f"Domain: {dn}")
    if registrar: lines.append(f"Registrar: {registrar}")
    if created: lines.append(f"Created: {created}")
    if expires: lines.append(f"Expires: {expires}")
    if ns: lines.append(f"Name servers: {ns}")
    if status: lines.append(f"Status: {status}")

    raw_text = None
    try:
        raw_text = getattr(w, "text", None)
        if not raw_text:
            raw_text = json.dumps(w, ensure_ascii=False, default=str)
    except Exception:
        raw_text = None
    raw_text = _clean_whois_text(raw_text)

    return WhoisResult(True, "domain", domain, lines or ["(нет краткого резюме)"], raw_text=raw_text)


def _lookup_ip(ip: str, timeout: float) -> WhoisResult:
    try:
        obj = IPWhois(ip)
        res = obj.lookup_rdap(rate_limit_timeout=timeout, depth=1)
    except Exception as e:
        return WhoisResult(False, "ip", ip, [], error=f"RDAP error: {e}")

    asn = res.get("asn")
    asn_cc = res.get("asn_country_code")
    asn_desc = res.get("asn_description")
    net = res.get("network") or {}
    cidr = net.get("cidr")
    name = net.get("name")
    country = net.get("country")

    lines = []
    if asn: lines.append(f"ASN: {asn} ({asn_cc or '?'})")
    if asn_desc: lines.append(f"AS Org: {asn_desc}")
    if cidr: lines.append(f"Route: {cidr}")
    if name: lines.append(f"Net name: {name}")
    if country: lines.append(f"Country: {country}")

    raw_text = json.dumps(res, ensure_ascii=False)
    return WhoisResult(True, "ip", ip, lines or ["(нет краткого резюме)"], raw_text=raw_text)
