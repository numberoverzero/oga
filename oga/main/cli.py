"""Command line implementation of oga."""
import click
import pathlib

from typing import Optional

from oga.core import Config, Session


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
    asset = session.loop.run_until_complete(session.describe_asset(asset_id=asset))
    if verbose:
        print(asset, flush=True)
    else:
        summary = {
            "id": asset.id,
            "type": asset.type.value,
            "favorites": asset.favorites,
            "tags": len(asset.tags)
        }
        template = "{id} -- {type} {favorites} favorites, {tags} tags"
        print(template.format(**summary), flush=True)


@cli.command("download")
@click.argument("asset")
@click.pass_obj
def download_asset(session: Session, asset: str):
    """Download files for a single ASSET."""
    asset = session.loop.run_until_complete(session.describe_asset(asset_id=asset))
    session.loop.run_until_complete(session.download_asset(asset=asset))
