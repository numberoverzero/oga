import asyncio
import functools
from typing import AsyncGenerator, List, TypeVar


T = TypeVar("T")

__all__ = ["block_on", "collect"]


class _AsyncProxy:
    def __init__(self, __proxy, __loop: asyncio.BaseEventLoop):
        self.__proxy = __proxy
        self.__loop = __loop

    def __getattr__(self, func_name):
        func = getattr(self.__proxy, func_name)

        @functools.wraps(func)
        def call(*args, **kwargs):
            task = func(*args, **kwargs)
            return self.__loop.run_until_complete(task)
        return call


def block_on(obj, loop=None):
    if loop is None:
        loop = obj.loop
    return _AsyncProxy(obj, loop)


async def collect(generator: AsyncGenerator[T, None]) -> List[T]:
    results = []
    async for x in generator:
        results.append(x)
    return results


def _install_uvloop():
    try:
        import asyncio
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass


def enable_speedups():
    _install_uvloop()


enable_speedups()
