from django.core.cache import cache

from .services import get_last_local_license

CACHE_KEY_VALID   = "license:is_valid"
CACHE_KEY_OBJECT  = "license:object"
CACHE_KEY_WARNING = "license:warning"

# Aggressive TTLs — active licenses shouldn't be re-checked often
TTL_VALID    = 60 * 60         # 1 hour when valid
TTL_INVALID  = 30              # 30 sec when invalid (fast recovery)
TTL_OBJECT   = 60 * 60 * 24    # 24 h — the license row rarely changes


class LicenseChecker:
    # ------------------------------------------------------------
    # Cheap path — used by middleware on every request
    # ------------------------------------------------------------
    @classmethod
    def is_licensed(cls) -> bool:
        """
        Cached yes/no. No DB query on cache hit.
        Server is NEVER contacted here — that's the daily task.
        """
        cached = cache.get(CACHE_KEY_VALID)
        if cached is not None:
            return cached

        lic = cls.get_license(use_cache=False)
        result = bool(lic and lic.is_valid())

        cache.set(
            CACHE_KEY_VALID,
            result,
            TTL_VALID if result else TTL_INVALID,
        )
        return result

    # ------------------------------------------------------------
    # Slightly more expensive — cached for 24h
    # ------------------------------------------------------------
    @classmethod
    def get_license(cls, use_cache: bool = True):
        """
        Return the LocalLicense object, cached for 24h.
        Pass use_cache=False to force a DB hit (rare).
        """
        if use_cache:
            cached = cache.get(CACHE_KEY_OBJECT)
            if cached is not None:
                return cached

        lic = get_last_local_license()
        if lic is not None:
            cache.set(CACHE_KEY_OBJECT, lic, TTL_OBJECT)
        return lic

    # ------------------------------------------------------------
    # Invalidate everything — call after activate / re-verify / daily task
    # ------------------------------------------------------------
    @classmethod
    def invalidate_cache(cls) -> None:
        cache.delete(CACHE_KEY_VALID)
        cache.delete(CACHE_KEY_OBJECT)
        cache.delete(CACHE_KEY_WARNING)