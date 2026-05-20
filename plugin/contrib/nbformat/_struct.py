# Copyright (c) IPython Development Team.
# Distributed under the terms of the Modified BSD License.
# Trimmed for WriterAgent: attribute-style dict only (merge/conflict helpers removed).

from __future__ import annotations

from typing import Any

__all__ = ["Struct"]


class Struct(dict[Any, Any]):
    """Dict subclass with attribute-style access (vendored from nbformat)."""

    _allownew = True

    def __init__(self, *args, **kw):
        object.__setattr__(self, "_allownew", True)
        dict.__init__(self, *args, **kw)

    def __setitem__(self, key, value):
        if not self._allownew and key not in self:
            raise KeyError(f"can't create new attribute {key} when allow_new_attr(False)")
        dict.__setitem__(self, key, value)

    def __setattr__(self, key, value):
        if isinstance(key, str) and (key in self.__dict__ or hasattr(Struct, key)):
            raise AttributeError(f"attr {key} is a protected member of class Struct.")
        try:
            self.__setitem__(key, value)
        except KeyError as e:
            raise AttributeError(e) from None

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def update(self, *args, **kwargs):
        if len(args) > 1:
            raise TypeError(f"update expected at most 1 arguments, got {len(args)}")
        if args:
            other = args[0]
            if isinstance(other, dict):
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

    def copy(self):
        return Struct(dict.copy(self))
