from setuptools import find_packages, setup


setup(
    name="searxinstancesbot",
    version="0.1",
    packages=find_packages("src"),
    package_dir={"": "src"},
    include_package_data=True,
    install_requires=[
        "gidgethub==4.*",
        "cachetools==4.*",
        "httpx==0.*",
        "starlette==0.*",
        "uvloop==0.*",
        "uvicorn==0.*",
    ],
)
