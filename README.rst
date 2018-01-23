Download an asset in 5 lines:

.. code-block:: python

    >>> from oga.core import Session
    >>> session = Session()
    >>> asset_id = "imminent-threat"
    >>> asset = session.loop.run_until_complete(session.describe_asset(asset_id))
    >>> session.loop.run_until_complete(session.download_asset(asset))

Let's take advantage of the async client and download a few assets at once:

.. code-block:: python

    >>> import asyncio
    >>> from oga.core import Config, Session
    >>> config = Config.default()
    >>> config.max_conns = 200  # please be nice
    >>> session = Session(config)

    >>> async def download(asset_id):
    ...     asset = await session.describe_asset(asset_id)
    ...     await session.download_asset(asset)
    ...

    >>> asset_ids = [
    ...     "free-music-pack",
    ...     "battle-theme-a",
    ...     "rise-of-spirit",
    ...     "town-theme-rpg",
    ...     "soliloquy"]

    >>> task = asyncio.wait(
    ...     [download(id) for id in asset_ids],
    ...     loop=session.loop,
    ...     return_when=asyncio.ALL_COMPLETED)

    >>> session.loop.run_until_complete(task)
