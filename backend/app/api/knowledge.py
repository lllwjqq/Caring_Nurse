from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import DietRecommendation, Disease, DiseaseSymptom, Symptom, Treatment
from app.schemas import KGEdge, KGNode, KnowledgeGraphResponse

router = APIRouter(prefix="/knowledge", tags=["知识图谱"])


@router.get("/graph", response_model=KnowledgeGraphResponse)
async def get_knowledge_graph(db: AsyncSession = Depends(get_db)):
    diseases = (await db.execute(select(Disease))).scalars().all()
    symptoms = (await db.execute(select(Symptom))).scalars().all()
    treatments = (await db.execute(select(Treatment))).scalars().all()
    diets = (await db.execute(select(DietRecommendation))).scalars().all()
    links = (await db.execute(select(DiseaseSymptom))).scalars().all()

    nodes: list[KGNode] = []
    edges: list[KGEdge] = []

    for d in diseases:
        nodes.append(KGNode(id=f"d{d.id}", label=d.name, type="disease"))
    for s in symptoms:
        nodes.append(KGNode(id=f"s{s.id}", label=s.name, type="symptom"))
    for t in treatments:
        nodes.append(KGNode(id=f"t{t.id}", label=t.name, type="treatment"))
    for di in diets:
        nodes.append(KGNode(id=f"di{di.id}", label=di.food_category, type="diet"))

    for link in links:
        edges.append(KGEdge(source=f"d{link.disease_id}", target=f"s{link.symptom_id}", label="has_symptom"))
    for t in treatments:
        edges.append(KGEdge(source=f"d{t.disease_id}", target=f"t{t.id}", label="treatment"))
    for di in diets:
        edges.append(KGEdge(source=f"d{di.disease_id}", target=f"di{di.id}", label="diet_advice"))

    return KnowledgeGraphResponse(nodes=nodes, edges=edges)
