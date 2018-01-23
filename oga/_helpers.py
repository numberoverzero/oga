def _install_uvloop():
    try:
        import asyncio
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass


def enable_speedups():
    _install_uvloop()