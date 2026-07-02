#!/usr/bin/env python
"""
MySQL → Vector DB 동기화 스크립트

사용 예:
    python sync_vector_index.py
    python sync_vector_index.py --force
    python sync_vector_index.py --status
"""

from __future__ import annotations

import argparse
import json
import sys

from chatbot.embeddings import get_embedding_info, resolve_provider
from chatbot.vector_store import ensure_vector_index, get_vector_index


def main() -> int:
    parser = argparse.ArgumentParser(description="MySQL FAQ/페르소나 데이터를 Vector DB에 동기화합니다.")
    parser.add_argument("--force", action="store_true", help="변경 여부와 관계없이 전체 재색인")
    parser.add_argument("--status", action="store_true", help="현재 인덱스 상태만 출력")
    args = parser.parse_args()

    index = get_vector_index()
    if args.status:
        print(json.dumps(index.get_status(), ensure_ascii=False, indent=2))
        return 0

    info = get_embedding_info()
    print(f"[INFO] 임베딩 제공자: {info['provider']} / 모델: {info['model']}")

    try:
        result = ensure_vector_index(force=args.force)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        _print_help()
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        if result.get("hint"):
            print(result["hint"], file=sys.stderr)
        _print_help()
        return 1
    if result.get("skipped"):
        print("[OK] 변경 없음 — 기존 Vector 인덱스를 그대로 사용합니다.")
    else:
        print("[OK] Vector 인덱스 동기화 완료")
    return 0


def _print_help() -> None:
    provider = resolve_provider()
    print(
        "\n도움말:\n"
        "  1) OpenAI 할당량 부족 시 → .env 에 EMBEDDING_PROVIDER=local 추가\n"
        "  2) pip install sentence-transformers\n"
        "  3) python sync_vector_index.py --force\n"
        "  4) 의미 검색 없이 키워드만 쓰려면 → OPENAI_FAQ_EMBEDDING=0\n"
        f"  현재 provider 설정: {provider}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
