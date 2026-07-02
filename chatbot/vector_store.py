from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

from chatbot.embeddings import embed_query, embed_texts, get_embedding_info, is_embedding_enabled, resolve_provider
from db_config import get_engine

logger = logging.getLogger(__name__)

FAQ_COLLECTION = "company_faq"
PERSONA_COLLECTION = "persona_detail"
DEFAULT_PERSIST_DIR = Path("data/chroma")


class VectorIndex:
    def __init__(self, persist_dir: str | Path | None = None) -> None:
        self.persist_dir = Path(persist_dir or os.getenv("VECTOR_DB_PATH", DEFAULT_PERSIST_DIR))
        self.meta_path = self.persist_dir / "sync_meta.json"
        self._client = None
        self._faq_collection = None
        self._persona_collection = None

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError("chromadb 패키지가 필요합니다. pip install chromadb") from exc

        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self.persist_dir))
        self._faq_collection = self._client.get_or_create_collection(
            name=FAQ_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        self._persona_collection = self._client.get_or_create_collection(
            name=PERSONA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        return self._client

    @property
    def faq_collection(self):
        self._ensure_client()
        return self._faq_collection

    @property
    def persona_collection(self):
        self._ensure_client()
        return self._persona_collection

    def is_ready(self) -> bool:
        if not is_embedding_enabled():
            return False
        try:
            self._ensure_client()
            return self.faq_collection.count() > 0
        except Exception:
            return False

    def get_status(self) -> dict[str, Any]:
        info = get_embedding_info()
        status = {
            "embedding_enabled": is_embedding_enabled(),
            "embedding_provider": info.get("provider"),
            "embedding_model": info.get("model"),
            "persist_dir": str(self.persist_dir),
            "faq_count": 0,
            "persona_count": 0,
            "last_sync": None,
        }
        if self.meta_path.exists():
            try:
                status.update(json.loads(self.meta_path.read_text(encoding="utf-8")))
            except Exception:
                pass
        if status["embedding_enabled"]:
            try:
                self._ensure_client()
                status["faq_count"] = self.faq_collection.count()
                status["persona_count"] = self.persona_collection.count()
            except Exception as exc:
                status["error"] = type(exc).__name__
        return status

    def sync_from_mysql(self, force: bool = False) -> dict[str, Any]:
        if not is_embedding_enabled():
            return {"ok": False, "reason": "embedding_disabled"}

        engine = get_engine()
        with engine.connect() as conn:
            faq_df = pd.read_sql(
                "SELECT faq_id, company, car_category, question, answer, persona_tags "
                "FROM company_faq ORDER BY faq_id",
                conn,
            )
            try:
                persona_df = pd.read_sql(
                    "SELECT persona_code, persona_name, persona_keyword, persona_desc "
                    "FROM tbl_persona_detail ORDER BY persona_code",
                    conn,
                )
            except Exception:
                persona_df = pd.DataFrame()

        signature = self._build_signature(faq_df, persona_df)
        old_meta = self._read_meta()
        if not force and old_meta.get("signature") == signature:
            return {"ok": True, "skipped": True, "faq_count": len(faq_df), "persona_count": len(persona_df)}

        self._ensure_client()
        try:
            faq_synced = self._sync_faq_collection(faq_df)
            persona_synced = self._sync_persona_collection(persona_df)
        except Exception as exc:
            logger.exception("Vector sync failed")
            return {
                "ok": False,
                "reason": type(exc).__name__,
                "message": str(exc),
                "hint": (
                    "OpenAI 할당량이 부족하면 .env 에 EMBEDDING_PROVIDER=local 을 설정한 뒤 "
                    "pip install sentence-transformers 후 다시 실행하세요."
                ),
            }

        meta = {
            "signature": signature,
            "faq_count": faq_synced,
            "persona_count": persona_synced,
            "embedding_provider": resolve_provider(),
            "embedding_model": get_embedding_info().get("model"),
            "last_sync": datetime.now(timezone.utc).isoformat(),
        }
        self.meta_path.parent.mkdir(parents=True, exist_ok=True)
        self.meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Vector index synced: faq=%s persona=%s", faq_synced, persona_synced)
        return {"ok": True, "skipped": False, **meta}

    def search_faq(self, query: str, top_k: int = 5, company: str | None = None) -> list[dict[str, Any]]:
        if not self.is_ready():
            return []
        where = {"company": company} if company else None
        try:
            query_vec = embed_query(query)
            result = self.faq_collection.query(
                query_embeddings=[query_vec],
                n_results=max(top_k, 5),
                where=where,
                include=["metadatas", "documents", "distances"],
            )
        except Exception as exc:
            logger.warning("FAQ 벡터 검색 실패: %s", type(exc).__name__)
            return []

        rows: list[dict[str, Any]] = []
        metas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        for meta, dist in zip(metas, distances):
            if not meta:
                continue
            rows.append(
                {
                    "faq_id": int(meta.get("faq_id", 0)),
                    "company": meta.get("company", ""),
                    "car_category": meta.get("car_category", ""),
                    "question": meta.get("question", ""),
                    "answer": meta.get("answer", ""),
                    "persona_tags": meta.get("persona_tags", ""),
                    "_semantic_score": _distance_to_score(dist),
                }
            )
        return rows[:top_k]

    def search_persona(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        if not self.is_ready():
            return []
        try:
            query_vec = embed_query(query)
            result = self.persona_collection.query(
                query_embeddings=[query_vec],
                n_results=max(top_k, 3),
                include=["metadatas", "distances"],
            )
        except Exception as exc:
            logger.warning("페르소나 벡터 검색 실패: %s", type(exc).__name__)
            return []

        rows: list[dict[str, Any]] = []
        metas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        for meta, dist in zip(metas, distances):
            if not meta:
                continue
            rows.append(
                {
                    "persona_code": meta.get("persona_code", ""),
                    "persona_name": meta.get("persona_name", ""),
                    "persona_keyword": meta.get("persona_keyword", ""),
                    "persona_desc": meta.get("persona_desc", ""),
                    "_semantic_score": _distance_to_score(dist),
                }
            )
        return rows[:top_k]

    def _sync_faq_collection(self, faq_df: pd.DataFrame) -> int:
        collection = self.faq_collection
        if faq_df.empty:
            self._reset_collection(FAQ_COLLECTION)
            return 0

        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict[str, str]] = []
        for row in faq_df.itertuples(index=False):
            faq_id = int(getattr(row, "faq_id"))
            company = _safe_str(getattr(row, "company", ""))
            category = _safe_str(getattr(row, "car_category", ""))
            question = _safe_str(getattr(row, "question", ""))
            answer = _safe_str(getattr(row, "answer", ""))
            tags = _safe_str(getattr(row, "persona_tags", ""))
            ids.append(f"faq_{faq_id}")
            docs.append(f"[{company}] {category} Q: {question}\nA: {answer}\n태그: {tags}")
            metas.append(
                {
                    "faq_id": str(faq_id),
                    "company": company,
                    "car_category": category,
                    "question": question,
                    "answer": answer,
                    "persona_tags": tags,
                }
            )

        embeddings = embed_texts(docs)
        self._reset_collection(FAQ_COLLECTION)
        collection = self.faq_collection
        batch = 128
        for start in range(0, len(ids), batch):
            end = start + batch
            collection.add(
                ids=ids[start:end],
                documents=docs[start:end],
                metadatas=metas[start:end],
                embeddings=embeddings[start:end],
            )
        return len(ids)

    def _sync_persona_collection(self, persona_df: pd.DataFrame) -> int:
        collection = self.persona_collection
        if persona_df.empty:
            self._reset_collection(PERSONA_COLLECTION)
            return 0

        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict[str, str]] = []
        for row in persona_df.itertuples(index=False):
            code = _safe_str(getattr(row, "persona_code", "")).upper()
            name = _safe_str(getattr(row, "persona_name", ""))
            keyword = _safe_str(getattr(row, "persona_keyword", ""))
            desc = _safe_str(getattr(row, "persona_desc", ""))
            ids.append(f"persona_{code}")
            docs.append(f"{code} {name} 키워드: {keyword} 설명: {desc}")
            metas.append(
                {
                    "persona_code": code,
                    "persona_name": name,
                    "persona_keyword": keyword,
                    "persona_desc": desc,
                }
            )

        embeddings = embed_texts(docs)
        self._reset_collection(PERSONA_COLLECTION)
        collection = self.persona_collection
        batch = 128
        for start in range(0, len(ids), batch):
            end = start + batch
            collection.add(
                ids=ids[start:end],
                documents=docs[start:end],
                metadatas=metas[start:end],
                embeddings=embeddings[start:end],
            )
        return len(ids)

    def _reset_collection(self, name: str) -> None:
        try:
            self._client.delete_collection(name)
        except Exception:
            pass
        self._faq_collection = None
        self._persona_collection = None
        if name == FAQ_COLLECTION:
            self._faq_collection = self._client.get_or_create_collection(
                name=FAQ_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
        elif name == PERSONA_COLLECTION:
            self._persona_collection = self._client.get_or_create_collection(
                name=PERSONA_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )

    def _build_signature(self, faq_df: pd.DataFrame, persona_df: pd.DataFrame) -> str:
        payload = {
            "faq": len(faq_df),
            "persona": len(persona_df),
            "faq_tail": _safe_str(faq_df.iloc[-1].to_json()) if not faq_df.empty else "",
            "persona_tail": _safe_str(persona_df.iloc[-1].to_json()) if not persona_df.empty else "",
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def _read_meta(self) -> dict[str, Any]:
        if not self.meta_path.exists():
            return {}
        try:
            return json.loads(self.meta_path.read_text(encoding="utf-8"))
        except Exception:
            return {}


_index: VectorIndex | None = None


def get_vector_index() -> VectorIndex:
    global _index
    if _index is None:
        _index = VectorIndex()
    return _index


def ensure_vector_index(force: bool = False) -> dict[str, Any]:
    index = get_vector_index()
    return index.sync_from_mysql(force=force)


def _distance_to_score(distance: float | None) -> float:
    if distance is None:
        return 0.0
    # cosine distance in [0, 2] -> similarity in [0, 1]
    return max(0.0, min(1.0, 1.0 - float(distance)))


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
