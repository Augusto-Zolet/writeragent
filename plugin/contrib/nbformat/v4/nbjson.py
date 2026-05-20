# Copyright (c) IPython Development Team.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import copy
import json

from ..notebooknode import from_dict

from .rwbase import NotebookReader, NotebookWriter, rejoin_lines, split_lines, strip_transient


class BytesEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, bytes):
            return obj.decode("ascii")
        return json.JSONEncoder.default(self, obj)


class JSONReader(NotebookReader):
    def reads(self, s, **kwargs):
        nb = json.loads(s, **kwargs)
        return self.to_notebook(nb, **kwargs)

    def to_notebook(self, d, **kwargs):
        nb = from_dict(d)
        nb = rejoin_lines(nb)
        nb = strip_transient(nb)
        return nb


class JSONWriter(NotebookWriter):
    def writes(self, nb, **kwargs):
        kwargs["cls"] = BytesEncoder
        kwargs["indent"] = 1
        kwargs["sort_keys"] = True
        kwargs["separators"] = (",", ": ")
        kwargs.setdefault("ensure_ascii", False)
        nb = copy.deepcopy(nb)
        if kwargs.pop("split_lines", True):
            nb = split_lines(nb)
        nb = strip_transient(nb)
        return json.dumps(nb, **kwargs)


_reader = JSONReader()
_writer = JSONWriter()

reads = _reader.reads
read = _reader.read
to_notebook = _reader.to_notebook
write = _writer.write
writes = _writer.writes
