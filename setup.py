from setuptools import setup, find_packages

reqs = [
    "kivy",
    "pyperclip",
    "aiohttp"
]

setup(
    name="cam-flow",
    version='1.3',
    description="Manage testing of flow cells",
    author="jkr",
    author_email="jimmy.kjaersgaard@gmail.com",
    url="",
    install_requires=reqs,
    packages=find_packages(),
    use_scm_version=True,
    setup_requires=["setuptools_scm"],
    package_data={"": ["*.json","**/*.json"]},
    entry_points={"console_scripts": ["cam-flow = cam_flow.app:main",],},
)
