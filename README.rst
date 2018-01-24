OpenGameArt Asset Management
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Primarily exists to query and download assets from OpenGameArt.  This library does not manage collections, post or edit
comments.  In the future, it may be used to upload or modify your assets.

Downloading Assets
==================

The primary reason this library exists.  I was sick of clicking on each file in an asset.

One Asset
---------

Download an asset in 5 lines:

.. code-block:: python

    >>> from oga.core import Session
    >>> session = Session()
    >>> asset_id = "imminent-threat"
    >>> asset = session.loop.run_until_complete(session.describe_asset(asset_id))
    >>> session.loop.run_until_complete(session.download_asset(asset))

Multiple Assets
---------------

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

Caching
-------

This library uses a very simple (dumb) tracker to avoid re-downloading asset files based on the ``ETag`` of each
file.  Because OGA doesn't publish a content hash it's possible to modify the downloaded file and you'll break the
tracking.  Because the tracker is dumb, it doesn't even check if the file still exists in the target directory.  You
need to remove the tracking file itself to invalidate the cache.  (Pull Requests welcome!  Someone fix this, please!)

Searching For Assets
====================

Searches use asynchronous generators so that you don't need to fetch every result to begin processing them.

.. code-block:: python

    from oga.core import Session
    session = Session()

    # submitter name begins with or contains 'xmo'
    search = session.search(submitter="xmo")

    async def collect(async_generator):
        """Helper to block and collapse an async generator into a single list"""
        results = []
        async for result in async_generator:
            results.append(result)
        return results

    results = session.loop.run_until_complete(collect(search))
    print(results)
    # ['graveyard-and-crypt', 'my-blender-skins', 'posable-poultry']
