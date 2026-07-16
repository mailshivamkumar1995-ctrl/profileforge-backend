"""
Security utilities for ProfileForge AI.

This module provides hardened implementations of common security patterns:
- Trusted-proxy IP extraction (FINDING-001)
- Secure error response formatting
- SSRF prevention helpers with DNS resolution (SEC-003)
- Security header validation
"""
import ipaddress
import logging
import socket
from urllib.parse import urlparse

from django.conf import settings

logger = logging.getLogger(__name__)

# Trusted proxy IPs/CIDRs — override via TRUSTED_PROXY_IPS setting
# In production, set this to your load balancer's internal IP range.
_DEFAULT_TRUSTED_PROXIES = [
    "127.0.0.1",
    "::1",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
]


def get_trusted_proxy_cidrs() -> list:
    raw = getattr(settings, "TRUSTED_PROXY_IPS", _DEFAULT_TRUSTED_PROXIES)
    result = []
    for cidr in raw:
        try:
            result.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            logger.warning("Invalid TRUSTED_PROXY_IPS entry: %s", cidr)
    return result


def _is_trusted_proxy(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in network for network in get_trusted_proxy_cidrs())
    except ValueError:
        return False


def get_client_ip(request) -> str:
    """
    Extract the real client IP address from a request.

    Reads X-Forwarded-For only when the immediate connection comes from a
    trusted proxy. Falls back to REMOTE_ADDR for direct connections.

    This prevents IP spoofing by untrusted clients (FINDING-001).
    """
    remote_addr = request.META.get("REMOTE_ADDR", "")

    if not _is_trusted_proxy(remote_addr):
        return remote_addr

    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        # XFF format: "client, proxy1, proxy2"
        # Walk from right to find first non-trusted IP
        ips = [ip.strip() for ip in xff.split(",")]
        for ip in reversed(ips):
            if not _is_trusted_proxy(ip):
                return ip
        # All IPs in XFF are trusted — return leftmost (original client)
        return ips[0] if ips else remote_addr

    return remote_addr


# ── SSRF Prevention ───────────────────────────────────────────────────────────

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

_ALLOWED_URL_SCHEMES = {"https", "http"}


def _is_private_ip(ip_str: str) -> bool:
    """Return True if ip_str represents a private/reserved/loopback address."""
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in network for network in _PRIVATE_NETWORKS)
    except ValueError:
        return False


def is_safe_url(url: str, allowed_hosts: list[str] | None = None) -> bool:
    """
    Validate that a URL is safe to redirect to or fetch from.

    Prevents:
    - SSRF to internal services (including via DNS rebinding — SEC-003)
    - Open redirect to external hosts
    - Non-HTTP schemes (file://, ftp://, etc.)

    SEC-003 fix: DNS hostnames are resolved at validation time so that a
    hostname like evil.attacker.com that resolves to 169.254.169.254 (AWS
    metadata) is caught and blocked. Fail-closed: DNS resolution errors
    are treated as unsafe.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme.lower() not in _ALLOWED_URL_SCHEMES:
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    # If allowed_hosts specified, enforce allowlist
    if allowed_hosts and hostname not in allowed_hosts:
        return False

    # 1. If hostname is already an IP literal, check it directly.
    try:
        addr = ipaddress.ip_address(hostname)
        if _is_private_ip(str(addr)):
            return False
        return True
    except ValueError:
        pass  # Not an IP literal — fall through to DNS resolution

    # 2. Resolve DNS to catch rebinding attacks (SEC-003).
    #    Fail closed: if we cannot resolve the hostname, it is unsafe.
    try:
        # getaddrinfo returns all addresses (IPv4 and IPv6).
        results = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        logger.warning("SSRF check: DNS resolution failed for hostname %r — blocking", hostname)
        return False

    for _family, _type, _proto, _canonname, sockaddr in results:
        resolved_ip = sockaddr[0]
        if _is_private_ip(resolved_ip):
            logger.warning(
                "SSRF check: hostname %r resolved to private IP %s — blocking",
                hostname,
                resolved_ip,
            )
            return False

    return True


# ── Prompt injection mitigation ───────────────────────────────────────────────

def sanitize_user_content_for_prompt(content: str, max_length: int = 2000) -> str:
    """
    Wrap user-controlled content in XML-like delimiters to separate it from
    AI system prompt instructions. Truncate to max_length.

    This is a best-effort mitigation — prompt injection is an inherent LLM risk.
    """
    if not content:
        return ""
    truncated = content[:max_length]
    return f"<user_content>{truncated}</user_content>"
