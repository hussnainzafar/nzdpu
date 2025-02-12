"""
Holds the RedisClient class.
"""

from typing import Any

import redis.asyncio as redis
import structlog

import app.settings as settings

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# lots to disable because we get problems from parent
# pylint: disable = abstract-method, too-many-ancestors
# pylint: disable = invalid-overridden-method, arguments-renamed
# pylint: disable = arguments-differ, unsupported-binary-operation


class WisKeys:
    submission: str = "submission:"
    forms: str = "loaded_forms:"


class RedisClient(redis.Redis):
    """
    Redis client, subclassed from redis.Redis
    """

    wis_keys: WisKeys = WisKeys()

    def __init__(self, host: str, port: int, password: str, db: int = 0):
        """
        Init a subclassed instance of an async Redis client

        Args:
            host (str): Redis' host.
            port (_type_): Redis' port.
            password (_type_): Redis' password.
        """
        super().__init__(
            host=host,
            port=port,
            password=password,
            decode_responses=True,
            db=db,
        )
        self._cache_control = None
        self.key_prefix = "cached:"

    @property
    def cache_control(self):
        return self._cache_control

    @cache_control.setter
    def cache_control(self, value):
        self._cache_control = value

    async def disconnect(self):
        """
        Close the Redis connection
        """
        await self.connection_pool.disconnect()

    async def get(self, key: str) -> Any:
        """
        Get value of specified key.

        Args:
            key (str): The key in the Redis DB to get the value from.

        Returns:
            dict: The stored value, if any.
        """
        # always return None if redis not enabled
        if not bool(settings.cache.enabled):
            return None
        # check value of Cache-Control header
        # and return None on specific values
        match self.cache_control:
            case "no-cache":
                return None
            case "max-age=0":
                await self.del_pattern(key)
                return None

        key = self.key_prefix + key
        cached = await super().get(key)
        if cached:
            return cached

    async def set(
        self, key: str, data: str, ttl: int = settings.cache.ttl
    ) -> bool | None:
        """
        Set a value for the specified key, with a TTL.

        Args:
            key (str): The key where to store the value.
            data (dict): The data to store.
            ttl (int, optional): The TTL, after which the key will
                expire. Defaults to settings.REDIS_TTL.

        Returns:
            bool | None: True if successful.
        """
        key = self.key_prefix + key
        return await super().set(key, data, ex=ttl)

    async def del_pattern(self, pattern: str) -> None:
        """
        Deletes all keys matching against a pattern.

        Args:
            pattern (str): The key pattern to match.
        """
        # add key prefix and trailing glob to pattern
        pattern = self.key_prefix + pattern
        keys: list[str] = await self.keys(pattern)
        for key in keys:
            await self.delete(key)

    async def flushdb(self, asynchronous: bool = False):
        log.debug(f"Calling flushdb with asynchronous={asynchronous}")
        return await super().flushdb(asynchronous=asynchronous)
