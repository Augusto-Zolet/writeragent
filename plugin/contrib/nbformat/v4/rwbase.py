# Copyright (c) IPython Development Team.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations


def _is_json_mime(mime):
    return mime == "application/json" or (mime.startswith("application/") and mime.endswith("+json"))


def _rejoin_mimebundle(data):
    for key, value in list(data.items()):
        if not _is_json_mime(key) and isinstance(value, list) and all(isinstance(line, str) for line in value):
            data[key] = "".join(value)
    return data


def rejoin_lines(nb):
    """Rejoin multiline text split into string lists on disk (nbformat v4)."""
    for cell in nb.cells:
        if "source" in cell and isinstance(cell.source, list):
            cell.source = "".join(cell.source)

        attachments = cell.get("attachments", {})
        for _, attachment in attachments.items():
            _rejoin_mimebundle(attachment)

        if cell.get("cell_type", None) == "code":
            for output in cell.get("outputs", []):
                output_type = output.get("output_type", "")
                if output_type in {"execute_result", "display_data"}:
                    _rejoin_mimebundle(output.get("data", {}))
                elif output_type and isinstance(output.get("text", ""), list):
                    output.text = "".join(output.text)
    return nb


_non_text_split_mimes = {
    "application/javascript",
    "image/svg+xml",
}


def _split_mimebundle(data):
    for key, value in list(data.items()):
        if isinstance(value, str) and (key.startswith("text/") or key in _non_text_split_mimes):
            data[key] = value.splitlines(True)
    return data


def split_lines(nb):
    """Split multiline strings for VCS-friendly JSON export (inverse of rejoin_lines)."""
    for cell in nb.cells:
        source = cell.get("source", None)
        if isinstance(source, str):
            cell["source"] = source.splitlines(True)

        attachments = cell.get("attachments", {})
        for _, attachment in attachments.items():
            _split_mimebundle(attachment)

        if cell.cell_type == "code":
            for output in cell.outputs:
                if output.output_type in {"execute_result", "display_data"}:
                    _split_mimebundle(output.get("data", {}))
                elif output.output_type == "stream" and isinstance(output.text, str):
                    output.text = output.text.splitlines(True)
    return nb


def strip_transient(nb):
    """Remove transient metadata not meant for on-disk storage."""
    nb.metadata.pop("orig_nbformat", None)
    nb.metadata.pop("orig_nbformat_minor", None)
    nb.metadata.pop("signature", None)
    for cell in nb.cells:
        cell.metadata.pop("trusted", None)
    return nb


class NotebookReader:
    def reads(self, s, **kwargs):
        raise NotImplementedError("reads must be implemented in a subclass")

    def read(self, fp, **kwargs):
        return self.reads(fp.read(), **kwargs)


class NotebookWriter:
    def writes(self, nb, **kwargs):
        raise NotImplementedError("writes must be implemented in a subclass")

    def write(self, nb, fp, **kwargs):
        return fp.write(self.writes(nb, **kwargs))
