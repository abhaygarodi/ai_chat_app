from __future__ import annotations


class UpstreamServiceError(RuntimeError):
    """Base error for failures from external providers."""


class UpstreamUnavailableError(UpstreamServiceError):
    """Upstream provider is unavailable (network / connection / service down)."""
 
