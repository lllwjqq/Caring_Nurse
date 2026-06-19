from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeChunk
from app.services.llm_service import llm_service

SEED_KNOWLEDGE = [
    {
        "source": "中国2型糖尿病防治指南",
        "disease": "diabetes_type2",
        "title": "血糖控制目标",
        "content": "2型糖尿病患者空腹血糖控制目标一般为4.4-7.0 mmol/L，餐后2小时血糖<10.0 mmol/L，糖化血红蛋白<7.0%。老年或合并症患者可适当放宽。",
    },
    {
        "source": "中国高血压防治指南",
        "disease": "hypertension",
        "title": "血压控制目标",
        "content": "一般高血压患者血压控制目标为<140/90 mmHg。合并糖尿病、慢性肾病或蛋白尿患者建议<130/80 mmHg。65岁以上老年人可适当放宽至<150/90 mmHg。",
    },
    {
        "source": "中国高血压防治指南",
        "disease": "hypertension",
        "title": "头晕处理",
        "content": "高血压患者出现头晕时，应首先测量血压。如血压明显升高（≥180/110mmHg）需立即就医。头晕也可能与低血压、脑供血不足有关，需医生评估。",
    },
    {
        "source": "中国血脂异常防治指南",
        "disease": "hyperlipidemia",
        "title": "LDL-C控制目标",
        "content": "动脉粥样硬化性心血管疾病高危患者LDL-C目标值<2.6 mmol/L，极高危患者<1.8 mmol/L。生活方式干预包括低脂饮食、规律运动、控制体重。",
    },
    {
        "source": "慢性阻塞性肺疾病诊治指南",
        "disease": "copd",
        "title": "血氧监测",
        "content": "慢阻肺患者应定期监测血氧饱和度，静息状态下SpO2<90%需及时就医。避免吸烟和空气污染暴露，坚持肺康复训练。",
    },
    {
        "source": "慢病综合管理",
        "disease": "general",
        "title": "生活方式干预",
        "content": "慢病管理核心包括：合理膳食（低盐低脂低糖）、规律运动（每周≥150分钟中等强度）、戒烟限酒、规律作息、遵医嘱用药、定期复查。",
    },
]


class RAGService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _vector_literal(values: list[float]) -> str:
        return "[" + ",".join(f"{v:.8f}" for v in values) + "]"

    async def seed_knowledge(self):
        result = await self.db.execute(select(KnowledgeChunk).limit(1))
        if result.scalar_one_or_none():
            return
        for item in SEED_KNOWLEDGE:
            embedding = await llm_service.embed(item["content"])
            chunk = KnowledgeChunk(
                source=item["source"],
                disease=item["disease"],
                title=item["title"],
                content=item["content"],
                metadata_={"title": item["title"]},
            )
            if hasattr(KnowledgeChunk, "embedding"):
                chunk.embedding = embedding  # type: ignore
            self.db.add(chunk)
        await self.db.flush()

    async def search(self, query: str, disease: str | None = None, top_k: int = 3) -> list[dict]:
        await self.seed_knowledge()
        query_emb = await llm_service.embed(query)

        try:
            async with self.db.begin_nested():
                sql = """
                    SELECT id, source, disease, title, content,
                           1 - (embedding <=> :embedding::vector) as score
                    FROM knowledge_chunks
                    WHERE embedding IS NOT NULL
                """
                params: dict = {"embedding": self._vector_literal(query_emb)}
                if disease:
                    sql += " AND (disease = :disease OR disease = 'general')"
                    params["disease"] = disease
                sql += " ORDER BY embedding <=> :embedding::vector LIMIT :top_k"
                params["top_k"] = top_k
                result = await self.db.execute(text(sql), params)
                rows = result.fetchall()
                if rows:
                    return [
                        {"source": r.source, "title": r.title, "content": r.content, "score": float(r.score)}
                        for r in rows
                    ]
        except Exception:
            pass

        result = await self.db.execute(select(KnowledgeChunk))
        chunks = result.scalars().all()
        scored = []
        for c in chunks:
            if disease and c.disease not in (disease, "general"):
                continue
            score = sum(1 for w in query if w in c.content)
            scored.append((score, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"source": c.source, "title": c.title, "content": c.content, "score": s}
            for s, c in scored[:top_k]
        ]

    def format_context(self, chunks: list[dict]) -> str:
        if not chunks:
            return ""
        parts = []
        for i, c in enumerate(chunks, 1):
            parts.append(f"[{i}] {c['title']}（来源：{c['source']}）\n{c['content']}")
        return "\n\n".join(parts)
