"""
Analytics provider abstraction for Portfolio pages.

Designed for zero-cost switching between providers. Business logic never imports
a provider directly — it calls get_analytics_script() and receives ready HTML.
Adding a new provider requires only a new class + one entry in _REGISTRY.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Protocol


class IAnalyticsProvider(Protocol):
    def script_tag(self, analytics_id: str) -> str: ...
    def noscript_tag(self, analytics_id: str) -> str: ...


class BaseAnalyticsProvider(ABC):
    @abstractmethod
    def script_tag(self, analytics_id: str) -> str:
        """Returns the HTML <script> tag(s) to inject in <head>."""

    def noscript_tag(self, analytics_id: str) -> str:
        return ""


class NullAnalyticsProvider(BaseAnalyticsProvider):
    """No-op — analytics disabled."""

    def script_tag(self, analytics_id: str) -> str:
        return ""


class GoogleAnalyticsProvider(BaseAnalyticsProvider):
    def script_tag(self, analytics_id: str) -> str:
        return (
            f'<script async src="https://www.googletagmanager.com/gtag/js?id={analytics_id}"></script>\n'
            f"<script>\n"
            f"  window.dataLayer = window.dataLayer || [];\n"
            f"  function gtag(){{dataLayer.push(arguments);}}\n"
            f"  gtag('js', new Date());\n"
            f"  gtag('config', '{analytics_id}');\n"
            f"</script>"
        )


class PlausibleProvider(BaseAnalyticsProvider):
    def script_tag(self, analytics_id: str) -> str:
        # analytics_id is the domain, e.g. "mysite.com"
        return (
            f'<script defer data-domain="{analytics_id}" '
            f'src="https://plausible.io/js/script.js"></script>'
        )


class PostHogProvider(BaseAnalyticsProvider):
    def script_tag(self, analytics_id: str) -> str:
        # analytics_id is the PostHog project API key
        return (
            f"<script>\n"
            f"  !function(t,e){{var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a)"
            f"{{function g(t,e){{var o=e.split('.');2==o.length&&(t=t[o[0]],e=o[1]),"
            f"t[e]=function(){{t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}}}var p='capture identify alias people.set people.set_once set_config register "
            f"register_once unregister opt_out_capturing has_opted_out_capturing opt_in_capturing reset isFeatureEnabled onFeatureFlags'.split(' ');"
            f"for(var r=0;r<p.length;r++)g(e,p[r]);e._i.push([i,s,a])}},e.__SV=1)}}"
            f"(document,window.posthog||(window.posthog=[]));posthog.init('{analytics_id}',"
            f"{{api_host:'https://app.posthog.com'}});\n"
            f"</script>"
        )


_REGISTRY: dict[str, type[BaseAnalyticsProvider]] = {
    "none": NullAnalyticsProvider,
    "google_analytics": GoogleAnalyticsProvider,
    "plausible": PlausibleProvider,
    "posthog": PostHogProvider,
}


def get_analytics_script(provider_name: str, analytics_id: str) -> str:
    """Return the complete analytics HTML snippet for injection into the page <head>."""
    if not analytics_id or not provider_name or provider_name == "none":
        return ""
    provider_cls = _REGISTRY.get(provider_name, NullAnalyticsProvider)
    return provider_cls().script_tag(analytics_id)


def get_available_providers() -> list[str]:
    return [k for k in _REGISTRY if k != "none"]
