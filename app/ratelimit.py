"""Rate limiter (slowapi). When RATE_LIMIT_ENABLED is false this is a no-op
decorator so tests and minimal deployments don't need the machinery."""
from .config import settings

if settings.RATE_LIMIT_ENABLED:
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address)
else:

    class _NoOpLimiter:
        def limit(self, *args, **kwargs):
            def deco(fn):
                return fn

            return deco

    limiter = _NoOpLimiter()
