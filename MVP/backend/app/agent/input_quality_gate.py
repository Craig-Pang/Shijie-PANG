"""
输入质量门控（Input Quality Gate）
判断公告是否"值得分析"，在信息不足时拒绝分析
"""

from typing import Dict, Tuple, Literal, Optional
import re


def check_input_quality(
    raw_text: str,
    title: str = "",
    extracted_fields: Optional[Dict] = None
) -> Tuple[Literal["GOOD", "INSUFFICIENT"], Dict[str, any]]:
    """
    检查输入质量
    
    参数:
        raw_text: 公告正文
        title: 公告标题
        extracted_fields: 已提取的字段
    
    返回:
        (quality_status, quality_info)
        quality_status: "GOOD" 或 "INSUFFICIENT"
        quality_info: 包含检查详情的字典
    """
    if extracted_fields is None:
        extracted_fields = {}
    
    quality_info = {
        "text_length": len(raw_text),
        "has_location": False,
        "has_qualification": False,
        "has_scope": False,
        "has_deadline": False,
        "has_tonnage": False,
        "key_fields_count": 0,
        "reasons": []
    }
    
    # 检查 1: 文本长度
    if not raw_text or len(raw_text.strip()) < 300:
        quality_info["reasons"].append(f"正文过短（{len(raw_text)} 字符，要求 ≥300 字符）")
        return ("INSUFFICIENT", quality_info)
    
    # 检查 2: 关键字段提取
    full_text = (raw_text + " " + title).lower()
    
    # 检查地点
    location_keywords = ["地点", "位于", "建设地点", "项目地点", "工程地点", "施工地点"]
    if any(kw in full_text for kw in location_keywords):
        quality_info["has_location"] = True
        quality_info["key_fields_count"] += 1
    
    if extracted_fields.get("location"):
        quality_info["has_location"] = True
        quality_info["key_fields_count"] += 1
    
    # 检查资质要求
    qual_keywords = ["资质", "资格", "专业承包", "施工资质", "资质要求", "资格要求"]
    if any(kw in full_text for kw in qual_keywords):
        quality_info["has_qualification"] = True
        quality_info["key_fields_count"] += 1
    
    if extracted_fields.get("qualification"):
        quality_info["has_qualification"] = True
        quality_info["key_fields_count"] += 1
    
    # 检查项目范围
    scope_keywords = ["项目内容", "建设内容", "工程内容", "范围", "工程范围", "施工范围"]
    if any(kw in full_text for kw in scope_keywords):
        quality_info["has_scope"] = True
        quality_info["key_fields_count"] += 1
    
    if extracted_fields.get("scope"):
        quality_info["has_scope"] = True
        quality_info["key_fields_count"] += 1
    
    # 检查截止时间
    deadline_patterns = [
        r'投标截止',
        r'开标时间',
        r'报名截止',
        r'截止时间',
        r'\d{4}[-/]\d{1,2}[-/]\d{1,2}.*[前之前]'
    ]
    if any(re.search(pattern, full_text, re.I) for pattern in deadline_patterns):
        quality_info["has_deadline"] = True
        quality_info["key_fields_count"] += 1
    
    if extracted_fields.get("deadline"):
        quality_info["has_deadline"] = True
        quality_info["key_fields_count"] += 1
    
    # 检查吨位（可选，但如果有更好）
    tonnage_patterns = [
        r'\d+(?:\.\d+)?\s*[吨tT]',
        r'约\s*\d+(?:\.\d+)?\s*[吨tT]'
    ]
    if any(re.search(pattern, full_text, re.I) for pattern in tonnage_patterns):
        quality_info["has_tonnage"] = True
    
    if extracted_fields.get("tonnage"):
        quality_info["has_tonnage"] = True
    
    # 判断标准：至少需要 2 个关键字段（地点、资质、范围、截止时间）
    if quality_info["key_fields_count"] < 2:
        quality_info["reasons"].append(
            f"关键字段不足（仅 {quality_info['key_fields_count']} 个，要求 ≥2 个：地点/资质/范围/截止时间）"
        )
        return ("INSUFFICIENT", quality_info)
    
    # 通过检查
    quality_info["reasons"].append("输入质量良好，可以进行分析")
    return ("GOOD", quality_info)


def create_insufficient_info_result(
    rule_score: int,
    rule_reasons: list,
    quality_info: Dict
) -> Dict:
    """
    创建"信息不足"的分析结果
    
    参数:
        rule_score: 规则评分
        rule_reasons: 规则评分原因
        quality_info: 质量检查信息
    
    返回:
        分析结果字典
    """
    return {
        "decision_state": "UNKNOWN",
        "fit_label": "UNKNOWN",
        "fit_score": None,  # 明确为 null，不是 0
        "region_match": "UNKNOWN",
        "scope_match": "UNKNOWN",
        "scale_match": "UNKNOWN",
        "qualification_match": "UNKNOWN",
        "summary": f"公告信息不足，无法判断是否匹配公司业务。质量检查：{'; '.join(quality_info['reasons'])}。规则评分：{rule_score}/100。需人工确认或等待后续补充公告。",
        "reasons": rule_reasons + [f"输入质量不足：{'; '.join(quality_info['reasons'])}"],
        "risk_flags": ["信息不足，无法做出可靠判断"] + (["规则评分较低"] if rule_score < 20 else []),
        "key_fields": {
            "location": "",
            "scope": "",
            "deadline": "",
            "tonnage": "",
            "qualification": ""
        },
        "_meta": {
            "input_quality": "INSUFFICIENT",
            "decision_source": "QUALITY_GATE",
            "rule_score": rule_score
        }
    }

