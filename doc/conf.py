import os
import sys
sys.path.insert(0, os.path.abspath('..'))

project = 'mpmetrics'
copyright = '2022-23 Sean Anderson'
author = 'Sean Anderson'

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.intersphinx',
]

exclude_patterns = ['out']
html_theme = 'sphinx_rtd_theme'

intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
}
