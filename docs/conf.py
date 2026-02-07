"""Sphinx configuration for bac-py documentation."""

import importlib.metadata

project = "bac-py"
author = "bac-py contributors"
copyright = "2025, bac-py contributors"

version = importlib.metadata.version("bac_py")
release = version

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
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

# -- Intersphinx -------------------------------------------------------------

intersphinx_mapping = {
    "python": ("https://docs.python.org/3.13", None),
}

# -- HTML output -------------------------------------------------------------

html_theme = "furo"
html_static_path = ["_static"]
html_title = f"bac-py {version}"
