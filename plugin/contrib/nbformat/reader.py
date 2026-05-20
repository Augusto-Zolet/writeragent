# Copyright (c) IPython Development Team.
# Distributed under the terms of the Modified BSD License.
# WriterAgent: v4-only reader (v3 upgrade deferred).

from __future__ import annotations

import json


class NotJSONError(ValueError):
    """Raised when input is not valid JSON."""


class NBFormatError(ValueError):
    """Raised for unsupported or invalid notebook format."""


def parse_json(s, **kwargs):
    try:
        return json.loads(s, **kwargs)
    except ValueError as e:
        message = f"Notebook does not appear to be JSON: {s!r}"
        if len(message) > 80:
            message = message[:77] + "..."
        raise NotJSONError(message) from e


def get_version(nb):
    major = nb.get("nbformat", 1)
    minor = nb.get("nbformat_minor", 0)
    return (major, minor)


def reads(s, **kwargs):
    """Read a notebook JSON string into a NotebookNode (nbformat v4 only)."""
    from .v4.nbjson import to_notebook

    nb_dict = parse_json(s, **kwargs)
    major, _minor = get_version(nb_dict)
    if major != 4:
        raise NBFormatError(
            f"Unsupported nbformat version {major}; WriterAgent only supports v4 "
            "(v3 and older upgrade deferred — see docs/enabling_numpy_in_libreoffice.md)."
        )
    return to_notebook(nb_dict, **kwargs)


def read(fp, **kwargs):
    return reads(fp.read(), **kwargs)
