"""
构造 AI Prompt
强制 JSON 输出格式
"""

import json
from typing import Dict, List


def build_analysis_prompt(
    company_profile: Dict,
    rule_score: int,
    rule_reasons: List[str],
    rule_risk_flags: List[str],
    title: str,
    raw_text: str,
    extracted_fields: Dict = None
) -> str:
    """
    构造分析 Prompt
    
    参数:
        company_profile: 公司画像
        rule_score: 规则评分
        rule_reasons: 规则评分原因
        rule_risk_flags: 规则风险提示
        title: 招标标题
        raw_text: 招标正文
        extracted_fields: 已提取字段
    
    返回:
        prompt 字符串
    """
    
    # 格式化公司画像
    region_priority = ", ".join([
        f"{region}({score}分)" 
        for region, score in company_profile["region_priority"].items()
    ])
    
    project_types = "、".join(company_profile["project_types"])
    scale_range = company_profile["scale_range"]
    qualifications = "、".join(company_profile["qualifications"])
    
    # 格式化已提取字段
    fields_text = ""
    if extracted_fields:
        fields_text = "\n已提取字段：\n"
        for key, value in extracted_fields.items():
            if value:
                fields_text += f"- {key}: {value}\n"
    
    prompt = f"""你是一个专业的钢结构招标分析 AI。你的职责是：**基于规则引擎的事实判断结果，进行语义补充和综合评估**。

## 重要说明
- **规则引擎已完成了事实判断**（地域、规模、资质等硬性条件匹配度）
- **你的任务是语义补充**：结合公告的语义信息、上下文、隐含条件等，给出最终的综合判断
- **不要重复规则引擎的工作**：如果规则已明确判定不匹配，你应该尊重该判断
- **在信息不足时，必须诚实表达**：如果公告信息不足以做出判断，使用 UNKNOWN 状态，不要强行给出结论

## 公司业务画像
- 地域优先级：{region_priority}
- 项目类型：{project_types}
- 规模范围：目标约 {scale_range['target']} 吨（{scale_range['min']}-{scale_range['max']} 吨可接受）
- 资质：{qualifications}
- 业务偏向：钢结构制作/安装/运输/专业分包

## 规则评分结果（事实判断）
- 规则评分：{rule_score}/100
- 评分原因：{'; '.join(rule_reasons)}
- 风险提示：{'; '.join(rule_risk_flags) if rule_risk_flags else '无'}

## 招标公告
标题：{title}
{fields_text}
正文：
{raw_text[:3000]}

## 任务要求
1. **综合评估**：基于规则评分结果，结合公告的语义信息，给出最终适配度评分（0-100）
2. **确定决策状态**：
   - RECOMMEND：信息充分，明确匹配（≥70分）
   - REVIEW：信息充分，但不确定，需要人工复核（40-69分）
   - SKIP：信息充分，明确不匹配（<40分）
   - UNKNOWN：信息不足，无法判断（**这是一等状态，不是0分**）
3. **评估各项匹配度**：HIGH（高）、MED（中）、LOW（低）、UNKNOWN（未知）
4. **提取关键字段**：地点、范围、截止时间、吨位、资质要求
5. **生成分析摘要和推荐原因**
6. **识别风险提示**

## 输出格式（必须严格遵循，只输出 JSON，不要有任何解释性文字）
{{
  "decision_state": "<RECOMMEND|REVIEW|SKIP|UNKNOWN>",
  "fit_label": "<RECOMMEND|REVIEW|SKIP|UNKNOWN>",
  "fit_score": <0-100的整数，UNKNOWN时为null>,
  "region_match": "<HIGH|MED|LOW|UNKNOWN>",
  "scope_match": "<HIGH|MED|LOW|UNKNOWN>",
  "scale_match": "<HIGH|MED|LOW|UNKNOWN>",
  "qualification_match": "<HIGH|MED|LOW|UNKNOWN>",
  "summary": "<分析摘要，200字以内>",
  "reasons": ["<原因1>", "<原因2>", ...],
  "risk_flags": ["<风险1>", "<风险2>", ...],
  "key_fields": {{
    "location": "<项目地点>",
    "scope": "<项目范围/内容>",
    "deadline": "<投标截止时间>",
    "tonnage": "<钢结构吨位>",
    "qualification": "<所需资质要求>"
  }}
}}

## 注意事项
- 如果公告信息不足（缺少关键字段、正文过短等），必须使用 UNKNOWN 状态，fit_score 为 null
- 如果规则评分极低（<20分），不要强行输出 RECOMMEND
- 如果 summary 中出现"信息不足/不明确"等表述，不要给出高分（≥80分）
- decision_state 和 fit_label 必须一致

请直接输出 JSON，不要有任何其他文字。"""
    
    return prompt

