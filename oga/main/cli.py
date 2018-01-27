"""Command line implementation of oga."""
import pathlib
from typing import List, Optional

import click

from oga.core import Config, Session
from oga.primitives import AssetType


def init_config(
        config_path: Optional[str],
        root_dir: Optional[str],
        url: Optional[str],
        max_conns: Optional[int]) -> Config:
    config = Config.from_file(config_path)
    if root_dir is not None:
        config.root_dir = pathlib.Path(root_dir).expanduser()
    if url is not None:
        config.url = url
    if max_conns is not None:
        config.max_conns = max_conns
    return config


cli_type_map = {
    "2d": AssetType.ART_2D,
    "3d": AssetType.ART_3D,
    "concept": AssetType.CONCEPT_ART,
    "texture": AssetType.TEXTURE,
    "music": AssetType.MUSIC,
    "sfx": AssetType.SOUND_EFFECT,
    "doc": AssetType.DOCUMENT,
}
rev_cli_type_map = {v: k for k, v in cli_type_map.items()}


async def cli_describe(session: Session, asset_id: str, verbose: bool) -> str:
    asset = await session.describe_asset(asset_id=asset_id)
    if verbose:
        return str(asset)
    else:
        summary = {
            "id": asset.id,
            "type": rev_cli_type_map[asset.type],
            "favorites": asset.favorites,
            "tags": len(asset.tags)
        }
        template = "{id} {type} ({favorites} favorites, {tags} tags)"
        return template.format(**summary)


@click.group()
@click.option("--config-path", type=click.Path(exists=True, file_okay=True, dir_okay=False), required=False)
@click.option("--root-dir", type=click.Path(exists=False, dir_okay=True, file_okay=False))
@click.option("--url", type=str, required=False)
@click.option("--max-conns", type=int, required=False)
@click.pass_context
def cli(ctx, config_path: Optional[str], root_dir: Optional[str], url: Optional[str], max_conns: Optional[int]):
    """Search and download assets from OpenGameArt.org"""
    config = init_config(config_path, root_dir, url, max_conns)
    session = Session(config)
    ctx.obj = session


@cli.command("describe")
@click.argument("asset")
@click.option("--verbose/--summary", is_flag=True, default=False)
@click.pass_obj
def describe_asset(session: Session, asset: str, verbose: bool):
    """Look up a single ASSET."""
    description = session.loop.run_until_complete(cli_describe(session, asset, verbose))
    print(description, flush=True)


@cli.command("download")
@click.argument("asset")
@click.pass_obj
def download_asset(session: Session, asset: str):
    """Download files for a single ASSET."""
    asset = session.loop.run_until_complete(session.describe_asset(asset_id=asset))
    session.loop.run_until_complete(session.download_asset(asset=asset))


@cli.command("search")
@click.option("--verbose/--summary", is_flag=True, default=False)
@click.option("--keys", help="Search the whole page", type=str, default=None)
@click.option("--title", help="Search the asset title", type=str, default=None)
@click.option("--submitter", help="Search the submitter name", type=str, default=None)
@click.option("--sort-by", type=click.Choice(["favorites", "created", "views"]), default="favorites")
@click.option("--descending/--ascending", help="sort order", is_flag=True, default=True)
@click.option("--type", type=click.Choice(["2d", "3d", "concept", "texture", "music", "sfx", "doc"]), multiple=True)
@click.option("--tag", help="freeform tag", multiple=True, type=str)
@click.option("--tag-op", type=click.Choice(["or", "and", "not", "empty", "not-empty"]), default="or")
@click.pass_obj
def search_assets(
        session: Session, verbose: bool,
        keys: Optional[str], title: Optional[str], submitter: Optional[str],
        sort_by: str, descending: bool, type: List[str], tag: List[str], tag_op: str):
    """Search for an asset."""
    types = [cli_type_map[t] for t in type]
    search = session.search(
        keys=keys,
        title=title,
        submitter=submitter,
        sort_by=sort_by,
        descending=descending,
        types=types,
        tags=tag,
        tag_operation=tag_op
    )

    async def process():
        async for asset_id in search:
            description = await cli_describe(session, asset_id, verbose)
            print(description, flush=True)

    session.loop.run_until_complete(process())
