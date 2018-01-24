import asyncio
from typing import AsyncGenerator, List, TypeVar

T = TypeVar("T")

__all__ = ["block_on", "collect", "enable_speedups"]


class _AsyncProxy:
    def __init__(self, __proxy):
        assert hasattr(__proxy, "loop")
        self.__proxy = __proxy

    def __getattr__(self, func_name):
        def call(*args, **kwargs):
            loop = self.__proxy.loop  # type: asyncio.BaseEventLoop
            func = getattr(self.__proxy, func_name)
            task = func(*args, **kwargs)
            return loop.run_until_complete(task)
        return call


def block_on(obj):
    return _AsyncProxy(obj)


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
