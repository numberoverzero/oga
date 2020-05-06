import re
import urllib.parse
from typing import List

import bs4

from .primitives import AssetType, LicenseType


class Translations:
    license_search_values = {
        LicenseType.CC_BY_40: "17981",
        LicenseType.CC_BY_30: "2",
        LicenseType.CC_BY_SA_40: "17982",
        LicenseType.CC_BY_SA_30: "3",
        LicenseType.GPL_30: "6",
        LicenseType.GPL_20: "5",
        LicenseType.OGA_BY_30: "10310",
        LicenseType.CC0: "4",
        LicenseType.LGPL_30: "8",
        LicenseType.LGPL_21: "7",
    }

    asset_type_search_values = {
        AssetType.ART_2D: "9",
        AssetType.ART_3D: "10",
        AssetType.CONCEPT_ART: "7273",
        AssetType.TEXTURE: "14",
        AssetType.MUSIC: "12",
        AssetType.SOUND_EFFECT: "13",
        AssetType.DOCUMENT: "11",
    }


def parse_asset(asset_id: str, data: bytes) -> dict:
    text = data.decode("utf-8")
    soup = bs4.BeautifulSoup(text, "html.parser")

    # 0) author
    authors = soup.find_all(class_="field-name-author-submitter")
    assert len(authors) == 1
    authors = authors[0].find_all("a")
    for maybe_author in authors:
        if maybe_author["href"].startswith("/users/"):
            author = maybe_author["href"][7:]
            break
    else:
        author = None

    # 1) type
    types = soup.find_all(class_="field-name-field-art-type")
    assert len(types) == 1
    type = AssetType(types[0].a.text)

    # 2) licenses
    license_section = soup.find_all(class_="field-name-field-art-licenses")
    assert len(license_section) == 1
    licenses = [
        LicenseType(license.text)
        for license in license_section[0].find_all(class_="license-name")]

    # 3) tags
    tags_section = soup.find_all(class_="field-name-field-art-tags")
    assert len(tags_section) == 1
    tags = [tag.text for tag in tags_section[0].find_all("a")]

    # 4) favorites
    favorites_section = soup.find_all(class_="field-name-favorites")
    assert len(favorites_section) == 1
    favorites = int(favorites_section[0].find(class_="field-item").text)

    # 5) files
    files_section = soup.find_all(class_="field-name-field-art-files")
    assert len(files_section) == 1
    files = []
    for container_el in files_section[0].find_all(class_="file"):
        url = container_el.a["href"]
        file_id = urllib.parse.unquote(url).split("/sites/default/files/")[-1]
        files.append(file_id)

    # 6) attribution
    attribution_section = soup.select('.field-name-field-art-attribution .field-items')
    attribution = None
    if len(attribution_section) == 1:
        attribution = attribution_section[0].text.strip()
    
    return {
        "id": asset_id,
        "author": author,
        "type": type,
        "licenses": licenses,
        "tags": tags,
        "favorites": favorites,
        "files": files,
        "attribution": attribution
    }


def parse_search_results(data: bytes) -> List[str]:
    text = data.decode("utf-8")
    soup = bs4.BeautifulSoup(text, "html.parser")
    containers = soup.find_all(class_="view-display-id-search_art_advanced")
    asset_ids = []
    if len(containers) == 0:
        return asset_ids
    assert len(containers) == 1
    container = containers[0]
    spans = container.find_all("span", class_="art-preview-title")
    for span in spans:
        url = span.a["href"]  # type: str
        assert url.startswith("/content/")
        asset_ids.append(url[9:])
    return asset_ids


def parse_last_search_page(data: bytes) -> int:
    text = data.decode("utf-8")
    soup = bs4.BeautifulSoup(text, "html.parser")
    pagers = soup.find_all(class_="pager-last")
    if not pagers:
        return 0  # there is only one page, it just happens to be empty
    assert len(pagers) == 1
    pager = pagers[0]
    url = pager.a["href"]
    page_regex = re.compile("&page=(?P<page>[0-9]+)")
    match = page_regex.search(url)
    assert match
    return int(match.groupdict()["page"])
