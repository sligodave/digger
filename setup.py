try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(
    name="digger",
    description="Digger : A simple scraping helper.",
    license="MIT",
    version="0.1",
    author="David Higgins",
    author_email="sligodave@gmail.com",
    maintainer="David Higgins",
    maintainer_email="sligodave@gmail.com",
    url="https://github.com/sligodave/digger",
    packages=['digger'],
    install_requires=['requests']
)
