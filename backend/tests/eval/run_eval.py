"""Agent 评估脚本（规格 §11 / §14.6）。

用法（在 backend 目录）：
    python tests/eval/run_eval.py                 # 规则红旗 + 关键词/向量 RAG
    python tests/eval/run_eval.py --llm           # 红旗增加 LLM 复核
    python tests/eval/run_eval.py --mode keyword  # 只跑关键词 RAG

输出：红旗 TP/FP/FN/TN、召回、精确；RAG Hit@3。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app.database import AsyncSessionLocal  # noqa: E402
from app.graph.orchestrator import (  # noqa: E402
    _llm_safety_review,
    decide_safety,
    recall_red_flags,
)
from app.services.llm_service import llm_service  # noqa: E402
from app.services.rag_service import RAGService  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent


def load_json(name: str):
    with (EVAL_DIR / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


async def eval_red_flags(use_llm: bool) -> None:
    cases = load_json("red_flag_cases.json")
    tp = fp = fn = tn = 0
    for case in cases:
        hits = recall_red_flags(case["text"])
        review = None
        if use_llm:
            review = await _llm_safety_review(
                case["text"], [h["term"] for h in hits], []
            )
        predicted, _decision, _reason = decide_safety(hits, review)
        expected = bool(case["expected"])
        if predicted and expected:
            tp += 1
        elif predicted and not expected:
            fp += 1
        elif not predicted and expected:
            fn += 1
        else:
            tn += 1

    recall = tp / (tp + fn) if (tp + fn) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    mode = "rules+LLM" if (use_llm and llm_service.is_available) else "rules"
    print(f"\n[Safety:{mode}] cases={len(cases)} TP={tp} FP={fp} FN={fn} TN={tn}")
    print(f"[Safety:{mode}] recall={recall:.3f} precision={precision:.3f}")


async def eval_rag(mode: str) -> None:
    queries = load_json("rag_queries.json")
    try:
        async with AsyncSessionLocal() as db:
            rag = RAGService(db)
            hit = 0
            for item in queries:
                results = await rag.search(
                    item["query"], top_k=3, force_keyword=(mode == "keyword")
                )
                titles = [str(r.get("title", "")) for r in results]
                expected = str(item["title"])
                if any(expected in title or title in expected for title in titles):
                    hit += 1
            hit_at_3 = hit / len(queries) if queries else 0.0
            print(f"[RAG:{mode}] queries={len(queries)} hit@3={hit_at_3:.3f}")
    except Exception as exc:  # 数据库不可用时跳过
        print(f"[RAG:{mode}] skipped: {type(exc).__name__}: {exc}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="红旗增加 LLM 复核")
    parser.add_argument(
        "--mode", choices=["keyword", "vector", "both"], default="both",
        help="RAG 检索方式",
    )
    args = parser.parse_args()

    print(f"llm_key_set={llm_service.is_available}")
    await eval_red_flags(args.llm)
    if args.mode in ("keyword", "both"):
        await eval_rag("keyword")
    if args.mode in ("vector", "both"):
        await eval_rag("vector")


if __name__ == "__main__":
    asyncio.run(main())
