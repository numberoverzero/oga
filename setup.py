import os
import pathlib
from setuptools import setup, find_packages

HERE = pathlib.Path(os.path.abspath(os.path.dirname(__file__)))
README = (HERE / "README.rst").read_text()
VERSION = "VERSION-NOT-FOUND"
for line in (HERE / "oga" / "__init__.py").read_text().split("\n"):
    if line.startswith("__version__"):
        VERSION = eval(line.split("=")[-1])

REQUIREMENTS = [
    "aiohttp>=3.6",
    "beautifulsoup4>=4.9",
    "click>=7.1"
]

if __name__ == "__main__":
    setup(
        name="oga",
        version=VERSION,
        description="Library for interacting with OpenGameArt.org assets",
        long_description=README,
        author="Joe Cross",
        author_email="joe.mcross@gmail.com",
        url="https://github.com/numberoverzero/oga",
        license="MIT",
        platforms="any",
        include_package_data=True,
        packages=find_packages(exclude=("docs", "examples", "scripts", "tests")),
        install_requires=REQUIREMENTS,
        entry_points={
            "console_scripts": [
                "oga = oga.main.cli:cli"
            ]
        }
    )
