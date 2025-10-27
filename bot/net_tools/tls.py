from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
import socket
import ssl
import datetime as dt
import tempfile
import os

@dataclass
class TlsInfo:
    ok: bool
    host: str
    port: int

    # параметры сеанса
    protocol: Optional[str] = None
    cipher: Optional[str] = None

    # сертификат (leaf)
    subject_cn: Optional[str] = None
    issuer_cn: Optional[str] = None
    issuer_full: Optional[str] = None
    serial: Optional[str] = None
    san: List[str] | None = None

    not_before: Optional[str] = None   # YYYY-MM-DD (UTC)
    not_after: Optional[str] = None    # YYYY-MM-DD (UTC)
    days_left: Optional[int] = None
    hostname_ok: Optional[bool] = None

    # AIA
    ocsp_urls: List[str] | None = None
    ca_issuers: List[str] | None = None

    error: Optional[str] = None


_OPENSSL_TIME_FMT = "%b %d %H:%M:%S %Y %Z"  # e.g. "Jun  1 12:00:00 2025 GMT"

def _parse_cert_time(s: str | None) -> Optional[dt.datetime]:
    if not s:
        return None
    try:
        return dt.datetime.strptime(s, _OPENSSL_TIME_FMT)
    except Exception:
        return None

def _fmt_date_utc(d: Optional[dt.datetime]) -> Optional[str]:
    if not d:
        return None
    return d.strftime("%Y-%m-%d")

def _decode_cert_via_file(der_bytes: bytes) -> Optional[dict]:
    """
    Надёжный способ получить разбор сертификата, даже при CERT_NONE:
    сохраняем PEM во временный файл и просим CPython его декодировать.
    """
    try:
        pem = ssl.DER_cert_to_PEM_cert(der_bytes)
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(pem)
            path = f.name
        try:
            # внутренний декодер CPython (стабилен для диагностики)
            return ssl._ssl._test_decode_cert(path)  # type: ignore[attr-defined]
        finally:
            try:
                os.remove(path)
            except Exception:
                pass
    except Exception:
        return None

def _extract_fields(cert: dict) -> dict:
    # subject CN
    cn = None
    for rdn in cert.get("subject", []):
        for k, v in rdn:
            if k.lower() == "commonname":
                cn = v
                break

    # issuer CN + полный DN
    issuer_cn = None
    issuer_full_parts: list[str] = []
    for rdn in cert.get("issuer", []):
        for k, v in rdn:
            if k.lower() == "commonname":
                issuer_cn = v
            issuer_full_parts.append(f"{k}={v}")
    issuer_full = ", ".join(issuer_full_parts) if issuer_full_parts else None

    # SAN
    san_entries = []
    for k, v in cert.get("subjectAltName", []):
        if k.lower() in ("dns", "ip address"):
            san_entries.append(v)

    serial = cert.get("serialNumber")

    ocsp_raw = cert.get("OCSP")
    ocsp_urls = list(ocsp_raw) if isinstance(ocsp_raw, (list, tuple)) else ([ocsp_raw] if isinstance(ocsp_raw, str) else [])
    ca_issuers_raw = cert.get("caIssuers")
    ca_issuers = list(ca_issuers_raw) if isinstance(ca_issuers_raw, (list, tuple)) else ([ca_issuers_raw] if isinstance(ca_issuers_raw, str) else [])

    nb_dt = _parse_cert_time(cert.get("notBefore"))
    na_dt = _parse_cert_time(cert.get("notAfter"))
    days_left = (na_dt - dt.datetime.utcnow()).days if na_dt else None

    return dict(
        subject_cn=cn,
        issuer_cn=issuer_cn,
        issuer_full=issuer_full or None,
        san=san_entries or None,
        serial=serial,
        not_before=_fmt_date_utc(nb_dt),
        not_after=_fmt_date_utc(na_dt),
        days_left=days_left,
        ocsp_urls=ocsp_urls or None,
        ca_issuers=ca_issuers or None,
    )

def fetch(host: str, port: int = 443, timeout: float = 7.0) -> TlsInfo:
    """
    TLS-хэндшейк с SNI и извлечение полной информации о сертификате (leaf).
    Проверка цепочки отключена — нужна диагностическая сводка даже для self-signed.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                # версия TLS и шифр
                try:
                    protocol = ssock.version()
                except Exception:
                    protocol = None
                try:
                    cipher = ssock.cipher()
                    cipher_name = cipher[0] if cipher else None
                except Exception:
                    cipher_name = None

                # Пытаемся получить "богатый" словарь
                cert_dict = ssock.getpeercert()
                # Если он пустой/урезанный — сделаем разбор из DER
                if not cert_dict or not cert_dict.get("subject"):
                    der = ssock.getpeercert(binary_form=True)
                    if der:
                        decoded = _decode_cert_via_file(der)
                        if decoded:
                            cert_dict = decoded
    except Exception as e:
        return TlsInfo(ok=False, host=host, port=port, error=f"Handshake error: {e}")

    # Если даже после попытки декодирования данных нет — вернём хоть сессию
    if not cert_dict:
        return TlsInfo(
            ok=True, host=host, port=port,
            protocol=protocol, cipher=cipher_name,
            error="Не удалось получить данные сертификата (peercert empty)"
        )

    fields = _extract_fields(cert_dict)

    # Проверка совпадения имени хоста (без верификации цепочки)
    hostname_ok: Optional[bool]
    try:
        ssl.match_hostname(cert_dict, host)
        hostname_ok = True
    except ssl.CertificateError:
        hostname_ok = False
    except Exception:
        hostname_ok = None

    return TlsInfo(
        ok=True,
        host=host,
        port=port,
        protocol=protocol,
        cipher=cipher_name,
        hostname_ok=hostname_ok,
        **fields,
    )
