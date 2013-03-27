#!/usr/bin/env python

from setuptools import setup, find_packages

setup(name='infogami',
      version="0.5dev",
      description='Infogami: A new kind of wiki',
      author='Anand Chitipothu',
      author_email='anandology@gmail.com',
      url=' http://infogami.org/',
      packages=find_packages(exclude=["ez_setup"]),
      license="AGPLv3",
      platforms=["any"])
