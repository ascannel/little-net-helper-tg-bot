from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import dns.resolver
import dns.reversename
import dns.exception
import dns.rdatatype

@dataclass
class DnsRecord:
    value: str
    ttl: Optional[int] = None

@dataclass
class DnsResult:
    ok: bool
    rrtype: str
    qname: str
    answers: List[DnsRecord]
    cname: Optional[str] = None
    resolver: Optional[str] = None
    error: Optional[str] = None

def _format_txt(rdata) -> str:
    # rdata.strings в dnspython<2.4, rdata.strings-like в новых версиях
    try:
        return rdata.to_text().strip('"')
    except Exception:
        try:
            return b"".join(rdata.strings).decode("utf-8", "replace")
        except Exception:
            return str(rdata)

def lookup(name: str, rrtype: str, timeout: float = 4.0) -> DnsResult:
    """
    Выполняет DNS-запрос rrtype для name.
    rrtype ∈ {A, AAAA, CNAME, MX, TXT, NS, PTR}
    Для PTR name может быть IPv4 — конвертируем в in-addr.arpa.
    """
    rrtype = rrtype.upper().strip()
    valid_types = {"A", "AAAA", "CNAME", "MX", "TXT", "NS", "PTR"}
    if rrtype not in valid_types:
        return DnsResult(False, rrtype, name, [], error="unsupported type")

    qname = name.strip().rstrip(".")
    if rrtype == "PTR":
        # qname — это IPv4: преобразуем в reverse
        try:
            rev = dns.reversename.from_address(qname)
            qname = rev.to_text().rstrip(".")
        except Exception:
            return DnsResult(False, rrtype, name, [], error="invalid IPv4 for PTR")

    resolver = dns.resolver.Resolver()
    resolver.lifetime = timeout  # общий таймаут
    resolver.timeout = timeout   # таймаут на один nameserver

    try:
        answer = resolver.resolve(qname, rrtype, lifetime=timeout)
        answers: list[DnsRecord] = []

        # ttl одинаков для набора ответов, но укажем на каждом для удобства
        ttl = getattr(answer.rrset, "ttl", None)
        cname = None
        try:
            cname = answer.canonical_name.to_text().rstrip(".") if answer.canonical_name else None
        except Exception:
            cname = None

        for rdata in answer:
            if rrtype == "A":
                answers.append(DnsRecord(rdata.address, ttl))
            elif rrtype == "AAAA":
                answers.append(DnsRecord(rdata.address, ttl))
            elif rrtype == "CNAME":
                answers.append(DnsRecord(rdata.target.to_text().rstrip("."), ttl))
            elif rrtype == "MX":
                answers.append(DnsRecord(f"{rdata.preference} {rdata.exchange.to_text().rstrip('.')}", ttl))
            elif rrtype == "TXT":
                answers.append(DnsRecord(_format_txt(rdata), ttl))
            elif rrtype == "NS":
                answers.append(DnsRecord(rdata.target.to_text().rstrip("."), ttl))
            elif rrtype == "PTR":
                answers.append(DnsRecord(rdata.target.to_text().rstrip("."), ttl))
            else:
                answers.append(DnsRecord(rdata.to_text(), ttl))

        ns_used = ",".join(getattr(resolver, "nameservers", []) or [])
        return DnsResult(True, rrtype, qname, answers, cname=cname, resolver=ns_used)
    except dns.resolver.NXDOMAIN:
        return DnsResult(False, rrtype, qname, [], error="NXDOMAIN (name does not exist)")
    except dns.resolver.NoAnswer:
        return DnsResult(False, rrtype, qname, [], error="No answer")
    except dns.resolver.Timeout:
        return DnsResult(False, rrtype, qname, [], error="Timeout")
    except dns.exception.DNSException as e:
        return DnsResult(False, rrtype, qname, [], error=f"DNS error: {e}")
    except Exception as e:
        return DnsResult(False, rrtype, qname, [], error=f"Unexpected error: {e}")