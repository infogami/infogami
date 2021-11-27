#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name='infogami',
    version="0.5dev",
    description='Infogami: A new kind of wiki',
    author='Anand Chitipothu',
    author_email='anandology@gmail.com',
    url=' http://infogami.org/',
    packages=find_packages(exclude=["ez_setup"]),
    classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: Implementation :: CPython',
    ],
    license="AGPLv3",
    platforms=["any"],
)
