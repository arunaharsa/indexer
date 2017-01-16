from distutils.core import setup

setup(
	name = 'dekoruma_indexer',
  version = '0.1.0',
  description = 'A package for indexer algolia',
  author = 'Dekoruma',
  author_email = 'hello@dekoruma.com',
  url = 'https://github.com/jekidekoruma/indexer', # use the URL to the github repo
  py_modules=['dekoruma_indexer.base_indexer']
)