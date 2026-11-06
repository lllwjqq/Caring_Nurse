"""处方剂量归一化回归：防止“规格 500mg”被抽成 dose=1mg。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.document_parser import normalise_parsed  # noqa: E402


def dose_of(raw: dict) -> tuple:
    parsed = normalise_parsed("prescription", {"medications": [raw]})
    med = parsed["medications"][0]
    return med.get("dose"), med.get("dose_unit")


cases = [
    ({"name": "阿莫西林胶囊", "spec": "500 mg", "dose": 1, "dose_unit": "mg"}, (500.0, "mg")),
    ({"name": "辛伐他汀片", "spec": "20 mg", "dose": 1, "dose_unit": "mg"}, (20.0, "mg")),
    ({"name": "阿司匹林肠溶片", "spec": "100mg/片", "dose": 1, "dose_unit": "片"}, (1.0, "片")),
    ({"name": "二甲双胍片", "spec": "500mg", "dose": None, "dose_unit": "mg"}, (500.0, "mg")),
    ({"name": "二甲双胍肠溶片", "dose": "0.5g"}, (0.5, "g")),
]

ok = True
for raw, expected in cases:
    actual = dose_of(raw)
    passed = actual == expected
    ok = ok and passed
    print("PASS" if passed else "FAIL", raw["name"], "expected=", expected, "actual=", actual)

print("OVERALL", "PASS" if ok else "FAIL")
