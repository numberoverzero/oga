OpenGameArt Asset Management
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Primarily exists to query and download assets from OpenGameArt.  This library does not manage collections, post or edit
comments.  In the future, it may be used to upload or modify your assets.

Installation
============

::

    pip install oga

Using the CLI
=============

The cli can be used for searching, downloading, and describing assets.

::

    $ oga --help
    Usage: oga [OPTIONS] COMMAND [ARGS]...

      Search and download assets from OpenGameArt.org

    Options:
      --config-path PATH
      --root-dir DIRECTORY
      --url TEXT
      --max-conns INTEGER
      --help                Show this message and exit.

    Commands:
      describe  Look up a single ASSET.
      download  Download files for a single ASSET.
      search    Search for an asset.

Sample Commands
---------------

Describe a single asset.  The asset id is everything after ``/content/`` in the OpenGameArt url::

    $ oga describe imminent-threat
    imminent-threat music (37 favorites, 22 tags)

Download a single asset::

    $ oga download imminent-threat

A simple per-file etag-based cache is used to avoid re-downloading the same blobs::

    $ time oga download imminent-threat

    real    0m8.443s
    user    0m1.944s
    sys	0m0.592s
    $ time oga download imminent-threat

    real    0m0.780s
    user    0m0.444s
    sys	0m0.080s

In the future, describe and download operations should be much faster for recently-queried packages since today,
the asset etag is not checked and the asset description is not cached (only the file etags are).

Search for assets::

    $ oga search --type music --tag epic --tag viking
    heroic-demise-updated-version music (86 favorites, 12 tags)
    battle-theme-a music (76 favorites, 6 tags)
    rise-of-spirit music (71 favorites, 4 tags)
    space-boss-battle-theme music (57 favorites, 31 tags)
    rpg-battle-theme-the-last-encounter-0 music (53 favorites, 26 tags)
    dark-descent music (44 favorites, 8 tags)
    dream-raid-cinematic-action-soundtrack music (44 favorites, 17 tags)
    space-orchestral music (41 favorites, 3 tags)
    # ...

    $ oga search --type music --tag epic --tag viking --tag-op and
    # no results with both tags!

    $ oga search --type music --license cc0 --tag epic
    battle-theme-a music (76 favorites, 6 tags)
    boss-battle-music music (19 favorites, 3 tags)
    new-sunrise music (9 favorites, 15 tags)
    the-rush music (8 favorites, 13 tags)
    # ...

Output Format
-------------

The default output for an asset is a short summary, which can be cut and piped to other commands.  Its format is::

    <asset_id> <type> (<\d+> favorites, <\d+> tags)

    # oga search --submitter xmo --type 3d --type texture
    graveyard-and-crypt 3d (10 favorites, 11 tags)
    my-blender-skins texture (7 favorites, 9 tags)
    posable-poultry 3d (6 favorites, 9 tags)

Using the usual tools, you can pipe this to other commands eg. download::

    oga search --submitter xmo --type 3d --type texture \
      | cut -d" " -f1 \
      | xargs -n1 oga download

More asset details are available using ``--verbose``::

    $ oga describe imminent-threat --verbose
    {
        "attribution": null,
        "author": "matthew-pablo",
        "favorites": 37,
        "files": [
            {
                "etag": "2e9386d-4f63b81cc5d00",
                "id": "Imminent Threat Collection.zip",
                "size": 48838765
            }
        ],
        "id": "imminent-threat",
        "licenses": [
            "CC-BY-SA 3.0"
        ],
        "tags": [
            "Action",
            "stealth",
            "Battle",
            "combat",
            "covert",
            "Rock",
            "hard",
            "metal",
            "hardcore",
            "piano",
            "soft",
            "scary",
            "horror",
            "suspense",
            "epic",
            "drumset",
            "title",
            "violent",
            "dark",
            "serious",
            "metal gear",
            "call of duty"
        ],
        "type": "Music"
    }

Using the Library
=================

Downloading Assets
------------------

One Asset
^^^^^^^^^

Download an asset in 5 lines:

.. code-block:: python

    >>> from oga import Session
    >>> session = Session()
    >>> asset_id = "imminent-threat"
    >>> asset = session.loop.run_until_complete(session.describe_asset(asset_id))
    >>> session.loop.run_until_complete(session.download_asset(asset))

Multiple Assets
^^^^^^^^^^^^^^^

Let's take advantage of the async client and download a few assets at once:

.. code-block:: python

    >>> import asyncio
    >>> from oga import Config, Session
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
^^^^^^^

This library uses a very simple (dumb) tracker to avoid re-downloading asset files based on the ``ETag`` of each
file.  Because OGA doesn't publish a content hash it's possible to modify the downloaded file and you'll break the
tracking.

Searching For Assets
--------------------

Searches use asynchronous generators so that you don't need to fetch every result to begin processing them.

.. code-block:: python

    from oga import Session
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

Synchronous Client
------------------

The synchronous client exposes batched operations of ``Session.download_asset`` and ``Session.describe_asset``.


.. code-block:: python

    >>> from oga import SynchronizedSession
    >>> session = SynchronizedSession()
    >>> assets = session.batch_describe_assets([
    ...     "free-music-pack",
    ...     "battle-theme-a",
    ...     "rise-of-spirit",
    ...     "town-theme-rpg",
    ...     "soliloquy"
    ... ])
    >>> session.batch_download_assets(assets.values())

TODO
====

Roughly ordered by priority.

* docstrings
* community feature requests?
* unit tests
* rtd
* hook points for status updates (eg. progress bars for long downloads)
