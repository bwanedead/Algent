"""
The OPTIONAL dense ranker. Off by default (``flags.EMBEDDINGS_ENABLED``) and import-guarded: with the switch off, or a library missing, ``load()``
returns None and retrieval stays lexical. Nothing here is imported at module load; the heavy libraries are only touched inside ``load()``.

Backends (the maintainer installs ONE; see docs/architecture/markets-track-record.md):
* ``sentence-transformers``  ``google/embeddinggemma-300m`` (the reference implementation; asymmetric query/document prompts)
* ``fastembed``              ONNX runtime, lighter on RAM; works for the models the installed release supports

Vectors are cached on disk (``retrieval_store/embeddings.jsonl``, keyed by a hash of model + text), so a document is encoded once, ever.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Protocol

from . import flags


class Embedder(Protocol):
    name: str

    def encode(self, texts: list[str], *, query: bool = False) -> list[list[float]]: ...


def cache_path() -> Path:
    return Path(os.environ.get("ALGENT_RETRIEVAL_STORE") or "retrieval_store") / "embeddings.jsonl"


def _key(model: str, text: str) -> str:
    return hashlib.sha1(f"{model}\n{text}".encode()).hexdigest()[:20]


class _SentenceTransformers:
    def __init__(self, model: str) -> None:
        from sentence_transformers import SentenceTransformer           # noqa: PLC0415 - import-guarded by load()

        self.name, self._m = model, SentenceTransformer(model)

    def encode(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        if query and hasattr(self._m, "encode_query"):
            vecs = self._m.encode_query(texts, normalize_embeddings=True)
        elif not query and hasattr(self._m, "encode_document"):
            vecs = self._m.encode_document(texts, normalize_embeddings=True, batch_size=16)
        else:
            vecs = self._m.encode(texts, prompt_name="query" if query else "document", normalize_embeddings=True, batch_size=16)
        return [list(map(float, v)) for v in vecs]


class _FastEmbed:
    def __init__(self, model: str) -> None:
        from fastembed import TextEmbedding                             # noqa: PLC0415 - import-guarded by load()

        self.name, self._m = model, TextEmbedding(model_name=model)

    def encode(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        out = []
        for v in self._m.query_embed(texts) if query else self._m.embed(texts):
            n = sum(float(x) * float(x) for x in v) ** 0.5 or 1.0
            out.append([float(x) / n for x in v])
        return out


class CachedEmbedder:
    """Wraps a backend with the disk cache. ``encode`` of documents only computes the vectors not yet on file."""

    def __init__(self, inner: Embedder, path: Path | None = None) -> None:
        self.inner, self.name, self.path = inner, inner.name, path or cache_path()
        self.cache: dict[str, list[float]] = {}
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                self.cache[row["k"]] = row["v"]
        except (OSError, ValueError, KeyError):
            pass

    def encode(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        if query:                                                       # queries are one-offs: not worth caching
            return self.inner.encode(texts, query=True)
        keys = [_key(self.name, t) for t in texts]
        todo = [(k, t) for k, t in dict(zip(keys, texts, strict=True)).items() if k not in self.cache]
        if todo:
            fresh = self.inner.encode([t for _, t in todo])
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as fh:
                for (k, _), v in zip(todo, fresh, strict=True):
                    v = [round(x, 5) for x in v]
                    self.cache[k] = v
                    fh.write(json.dumps({"k": k, "v": v}) + "\n")
        return [self.cache[k] for k in keys]


def load(enabled: bool | None = None) -> CachedEmbedder | None:
    """The dense ranker, or None when switched off or its library is not installed (never raises)."""
    if not (flags.EMBEDDINGS_ENABLED if enabled is None else enabled):
        return None
    backend = _FastEmbed if flags.EMBED_BACKEND == "fastembed" else _SentenceTransformers
    try:
        return CachedEmbedder(backend(flags.EMBED_MODEL))
    except Exception:  # noqa: BLE001 - ImportError (not installed), a download or auth failure, out of memory: stay lexical
        return None
