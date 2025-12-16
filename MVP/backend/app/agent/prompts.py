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
    
    prompt = f"""你是一个专业的钢结构招标分析 AI。请分析以下招标公告，判断是否值得投标。

## 公司业务画像
- 地域优先级：{region_priority}
- 项目类型：{project_types}
- 规模范围：目标约 {scale_range['target']} 吨（{scale_range['min']}-{scale_range['max']} 吨可接受）
- 资质：{qualifications}
- 业务偏向：钢结构制作/安装/运输/专业分包

## 规则评分结果
- 规则评分：{rule_score}/100
- 评分原因：{'; '.join(rule_reasons)}
- 风险提示：{'; '.join(rule_risk_flags) if rule_risk_flags else '无'}

## 招标公告
标题：{title}
{fields_text}
正文：
{raw_text[:3000]}  # 限制长度避免过长

## 任务要求
1. 基于规则评分结果，结合招标公告内容，给出最终适配度评分（0-100）
2. 确定推荐标签：RECOMMEND（强烈推荐，≥70分）、REVIEW（需审核，40-69分）、SKIP（不推荐，<40分）
3. 评估各项匹配度：HIGH（高）、MED（中）、LOW（低）、UNKNOWN（未知）
4. 提取关键字段：地点、范围、截止时间、吨位、资质要求
5. 生成分析摘要和推荐原因
6. 识别风险提示

## 输出格式（必须严格遵循，只输出 JSON，不要有任何解释性文字）
{{
  "fit_score": <0-100的整数>,
  "fit_label": "<RECOMMEND|REVIEW|SKIP>",
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

请直接输出 JSON，不要有任何其他文字。"""
    
    return prompt

