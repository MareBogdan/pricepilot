"""Shared local embedding model (CLAUDE.md section 6: `sentence-transformers`, local, free --
no API spend). `paraphrase-multilingual-MiniLM-L12-v2`, 384-dim -- the SAME model and settings
`scripts/build_embeddings.py` uses for `norm_listings`. `scripts/build_policy_index.py` and
`src/pricepilot/policy/retrieval.py` both import `embed()` from here rather than each loading the
model their own way, because the index and the query embedding a mismatch away from each other is
a classic, silent RAG bug (cosine similarity between two different embedding spaces still returns
a number -- it is just meaningless).

`scripts/build_embeddings.py` itself is untouched and keeps its own inline copy of the loader
workaround below (Phase 3, ADR-0028): this module only serves the two NEW Phase 5 call sites, to
avoid touching already-reviewed Phase 3 code for an unrelated session.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from typing import Any

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384


def _load_sentence_transformer_class() -> Any:
    """Import `sentence_transformers.SentenceTransformer`, working around a Windows sandbox
    'Application Control' policy on this dev machine that blocks scikit-learn's compiled
    extensions (`sklearn.utils._array_api` -> `scipy.spatial._qhull` -> DLL load failure).
    `sentence_transformers` imports `sklearn.metrics` transitively for a similarity-metrics
    helper never touched by a plain `encode()` call, so the failure is an import-time artifact of
    this one machine's policy, not a real dependency of the encode path. Identical workaround to
    `scripts/build_embeddings.py`'s (verified bit-identical there:
    `docs/learned/phase3-embedding-equivalence-2026-09-17.md`) -- copied rather than imported from
    a `scripts/` module, since `src/` does not depend on `scripts/`."""
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer
    except ImportError:
        pass

    import importlib.abc
    import importlib.machinery

    def _make_stub(name: str) -> Any:
        mod = __import__("types").ModuleType(name)
        mod.__spec__ = importlib.machinery.ModuleSpec(name, loader=None, is_package=True)
        mod.__path__ = []

        def _getattr(attr: str) -> Any:
            def _raise(*_a: object, **_k: object) -> None:
                raise NotImplementedError(f"stubbed sklearn attr {attr!r} called")

            return _raise

        mod.__getattr__ = _getattr
        return mod

    class _SklearnStubFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
        def find_module(self, fullname: str, path: object = None) -> object:
            if fullname == "sklearn" or fullname.startswith("sklearn."):
                return self
            return None

        def load_module(self, fullname: str) -> Any:
            if fullname in sys.modules:
                return sys.modules[fullname]
            mod = _make_stub(fullname)
            sys.modules[fullname] = mod
            return mod

    print(
        "NOTE: normal `sentence_transformers` import failed (sklearn DLL block) -- "
        "installing a sklearn import stub for this process only. See "
        "docs/learned/phase3-embedding-equivalence-2026-09-17.md.",
        file=sys.stderr,
    )
    sys.meta_path.insert(0, _SklearnStubFinder())
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer


@lru_cache(maxsize=1)
def get_model() -> Any:
    """Loaded once per process. Retrieval calls `embed()` on every query -- reloading the model
    from disk on every call would be a real latency hit even though the model itself is free."""
    SentenceTransformer = _load_sentence_transformer_class()
    return SentenceTransformer(MODEL_NAME)


def embed(texts: list[str]) -> list[list[float]]:
    """Unit-normalized embeddings (`normalize_embeddings=True`, matching
    `scripts/build_embeddings.py` exactly) so pgvector's `<=>` cosine operator is directly
    comparable to vectors written by that script."""
    vectors = get_model().encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vectors]
