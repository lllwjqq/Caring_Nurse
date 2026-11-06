"""GSSC 轻量版上下文工程（规格 §9）。

分区：[Role] / [Patient Context] / [Evidence] / [History] / [Task] / [Output]
预算：max_tokens≈3000，中文按 1 字≈1 token，预留 20%。
超限：先丢最老历史，再截断 Evidence，最后截断患者上下文，并标注压缩。
"""

from __future__ import annotations

MAX_TOKENS = 3000
RESERVE_RATIO = 0.2
COMPRESS_MARK = "[... 内容已压缩 ...]"


def estimate_tokens(text: str) -> int:
    """中文 1 字≈1 token 的轻量估算（不引入 tiktoken）。"""
    return max(1, len(text or ""))


def _format_evidence(evidence: list[dict]) -> str:
    parts: list[str] = []
    for index, item in enumerate(evidence, 1):
        source = item.get("source") or ""
        title = item.get("title") or ""
        snippet = item.get("snippet") or ""
        parts.append(f"[{index}] {title}（{source}）\n{snippet}")
    return "\n\n".join(parts)


def build_context_messages(
    *,
    role: str,
    patient_context: str,
    evidence: list[dict] | None = None,
    history: list[dict] | None = None,
    task: str,
    output_hint: str = "",
    max_tokens: int = MAX_TOKENS,
) -> list[dict]:
    """按 token 预算组装 system + 历史 + task。"""
    evidence = evidence or []
    history = list(history or [])
    budget = max(200, int(max_tokens * (1 - RESERVE_RATIO)))
    task_text = f"[Task]\n用户：{task}"
    compressed = False

    evidence_text = _format_evidence(evidence)

    def build_system(ev_text: str, pc: str) -> str:
        parts = [f"[Role]\n{role}", f"[Patient Context]\n{pc}"]
        if ev_text:
            parts.append(f"[Evidence]\n{ev_text}")
        if output_hint:
            parts.append(f"[Output]\n{output_hint}")
        return "\n\n".join(parts)

    system = build_system(evidence_text, patient_context)

    def total_tokens() -> int:
        return (
            estimate_tokens(system)
            + estimate_tokens(task_text)
            + sum(estimate_tokens(str(m.get("content", ""))) for m in history)
        )

    # 1) 超预算先丢最老历史
    while history and total_tokens() > budget:
        history.pop(0)
        compressed = True

    # 2) 仍然超预算：截断 Evidence 片段
    if total_tokens() > budget and evidence:
        trimmed: list[dict] = []
        for item in evidence:
            copy = dict(item)
            copy["snippet"] = str(copy.get("snippet") or "")[:60]
            trimmed.append(copy)
        evidence_text = _format_evidence(trimmed)
        system = build_system(evidence_text, patient_context)
        compressed = True

    # 3) 最后截断患者上下文
    if total_tokens() > budget:
        fixed = (
            estimate_tokens(f"[Role]\n{role}")
            + estimate_tokens(evidence_text)
            + estimate_tokens(output_hint)
            + estimate_tokens(task_text)
            + 120
        )
        max_pc = max(80, budget - fixed)
        if len(patient_context) > max_pc:
            patient_context = patient_context[:max_pc] + "\n" + COMPRESS_MARK
            system = build_system(evidence_text, patient_context)
            compressed = True

    if compressed:
        system += f"\n\n{COMPRESS_MARK}"

    messages: list[dict] = [{"role": "system", "content": system}]
    messages.extend(history)
    messages.append({"role": "user", "content": task_text})
    return messages
