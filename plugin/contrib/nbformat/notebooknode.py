# Copyright (c) IPython Development Team.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from collections.abc import Mapping

from ._struct import Struct


class NotebookNode(Struct):
    """A dict-like node with attribute-access."""

    def __setitem__(self, key, value):
        if isinstance(value, Mapping) and not isinstance(value, NotebookNode):
            value = from_dict(value)
        super().__setitem__(key, value)

    def update(self, *args, **kwargs):
        if len(args) > 1:
            raise TypeError(f"update expected at most 1 arguments, got {len(args)}")
        if args:
            other = args[0]
            if isinstance(other, Mapping):
                for key in other:
                    self[key] = other[key]
            elif hasattr(other, "keys"):
                for key in other:
                    self[key] = other[key]
            else:
                for key, value in other:
                    self[key] = value
        for key, value in kwargs.items():
            self[key] = value


def from_dict(d):
    """Recursively convert dicts to NotebookNode (does not validate schema)."""
    if isinstance(d, dict):
        return NotebookNode({k: from_dict(v) for k, v in d.items()})
    if isinstance(d, (tuple, list)):
        return [from_dict(i) for i in d]
    return d
