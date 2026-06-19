# LoRA 微调预留目录（二期）
#
# 训练数据格式：
# {
#   "instruction": "患者有高血压，最近头晕，血压150/95，请给出建议",
#   "input": "患者档案：...",
#   "output": "根据指南建议..."
# }
#
# 使用 HuggingFace PEFT + 开源医学 LLM 进行 LoRA 微调
