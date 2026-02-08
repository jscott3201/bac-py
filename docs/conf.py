"""Sphinx configuration for bac-py documentation."""

import sys
from pathlib import Path

# -- Path setup --------------------------------------------------------------
# Add the source directory so autodoc can import modules without requiring
# the package to be installed.

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bac_py import __version__

project = "bac-py"
author = "bac-py contributors"
copyright = "2025, bac-py contributors"

version = __version__
release = version

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx_autodoc_typehints",
]

master_doc = "index"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
language = "en"

# -- Napoleon (Google-style docstrings) --------------------------------------

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_preprocess_types = True

# -- Autodoc -----------------------------------------------------------------

autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_typehints_format = "short"
autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
    "undoc-members": False,
}

# -- sphinx-autodoc-typehints ------------------------------------------------

always_use_bars_union = True
typehints_defaults = "braces"

# -- Intersphinx -------------------------------------------------------------

intersphinx_mapping = {
    "python": ("https://docs.python.org/3.13", None),
}

# -- HTML output -------------------------------------------------------------

html_theme = "furo"
html_static_path = ["_static"]
html_title = f"bac-py {version}"
