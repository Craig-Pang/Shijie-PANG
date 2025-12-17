"""
规则评分模块
独立于 LLM 的规则评分逻辑
"""

import re
import json
from typing import Dict, List, Tuple, Optional
from pathlib import Path


def load_company_profile() -> Dict:
    """加载公司画像配置"""
    profile_path = Path(__file__).parent / "company_profile.json"
    with open(profile_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_region_score(text: str, profile: Dict) -> Tuple[int, str]:
    """
    地域评分
    返回: (分数, 匹配的地域)
    """
    text_lower = text.lower()
    region_priority = profile["region_priority"]
    region_keywords = profile["region_keywords"]
    
    max_score = 0
    matched_region = "UNKNOWN"
    
    for region, score in region_priority.items():
        keywords = region_keywords.get(region, [])
        for keyword in keywords:
            if keyword in text:
                if score > max_score:
                    max_score = score
                    matched_region = region
                break
    
    return max_score, matched_region


def extract_tonnage(text: str) -> Optional[float]:
    """
    提取钢结构吨位
    支持多种格式：1000吨、1000t、约1000吨等
    """
    # 匹配数字+吨/t/T
    patterns = [
        r'(\d+(?:\.\d+)?)\s*[吨tT]',
        r'约\s*(\d+(?:\.\d+)?)\s*[吨tT]',
        r'(\d+(?:\.\d+)?)\s*吨位',
        r'钢结构.*?(\d+(?:\.\d+)?)\s*[吨tT]',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return float(match.group(1))
            except:
                continue
    
    return None


def score_scale(tonnage: Optional[float], profile: Dict) -> Tuple[int, str]:
    """
    规模评分
    返回: (分数, 匹配等级)
    """
    if tonnage is None:
        return 0, "UNKNOWN"
    
    scale_range = profile["scale_range"]
    min_ton = scale_range["min"]
    max_ton = scale_range["max"]
    optimal_min = scale_range["optimal_min"]
    optimal_max = scale_range["optimal_max"]
    target = scale_range["target"]
    
    if tonnage < min_ton or tonnage > max_ton:
        return 0, "LOW"
    
    # 接近目标值 1000 吨得分更高
    if optimal_min <= tonnage <= optimal_max:
        # 最接近 1000 吨得 30 分
        distance = abs(tonnage - target)
        score = max(0, 30 - int(distance / 10))
        return score, "HIGH"
    elif min_ton <= tonnage < optimal_min:
        # 200-800 吨，线性评分 0-20
        ratio = (tonnage - min_ton) / (optimal_min - min_ton)
        score = int(20 * ratio)
        return score, "MED" if score >= 10 else "LOW"
    else:  # optimal_max < tonnage <= max_ton
        # 1200-3000 吨，线性评分 20-0
        ratio = (max_ton - tonnage) / (max_ton - optimal_max)
        score = int(20 * ratio)
        return score, "MED" if score >= 10 else "LOW"


def score_scope(text: str, profile: Dict) -> Tuple[int, str]:
    """
    项目范围评分
    返回: (分数, 匹配等级)
    """
    text_lower = text.lower()
    project_keywords = profile["project_keywords"]
    preference_keywords = profile["preference_keywords"]
    
    score = 0
    
    # 检查项目类型关键词
    type_matched = False
    for project_type, keywords in project_keywords.items():
        for keyword in keywords:
            if keyword in text:
                score += 15
                type_matched = True
                break
        if type_matched:
            break
    
    # 检查业务偏好关键词
    preference_matched = False
    for keyword in preference_keywords:
        if keyword in text:
            score += 10
            preference_matched = True
            break
    
    if score >= 20:
        return score, "HIGH"
    elif score >= 10:
        return score, "MED"
    else:
        return score, "LOW"


def score_qualification(text: str, profile: Dict) -> Tuple[int, str]:
    """
    资质匹配评分
    返回: (分数, 匹配等级)
    """
    qualification_keywords = profile["qualification_keywords"]
    
    score = 0
    matched_quals = []
    
    for qual_type, keywords in qualification_keywords.items():
        for keyword in keywords:
            if keyword in text:
                score += 8
                matched_quals.append(qual_type)
                break
    
    if score >= 20:
        return score, "HIGH"
    elif score >= 8:
        return score, "MED"
    else:
        return score, "LOW"


def rule_score(
    raw_text: str,
    extracted_fields: Optional[Dict] = None
) -> Tuple[int, List[str], List[str]]:
    """
    规则评分主函数
    
    参数:
        raw_text: 招标公告原始文本
        extracted_fields: 已提取的字段（可选）
    
    返回:
        (rule_score, rule_reasons, rule_risk_flags)
    """
    profile = load_company_profile()
    
    # 合并文本（如果有 extracted_fields）
    full_text = raw_text
    if extracted_fields:
        full_text += " " + " ".join(str(v) for v in extracted_fields.values() if v)
    
    # 地域评分
    region_score, matched_region = extract_region_score(full_text, profile)
    
    # 规模评分
    tonnage = extract_tonnage(full_text)
    if extracted_fields and not tonnage:
        # 尝试从 extracted_fields 中提取
        tonnage_str = extracted_fields.get("tonnage") or extracted_fields.get("规模") or extracted_fields.get("重量")
        if tonnage_str:
            tonnage = extract_tonnage(str(tonnage_str))
    
    scale_score, scale_match = score_scale(tonnage, profile)
    
    # 范围评分
    scope_score, scope_match = score_scope(full_text, profile)
    
    # 资质评分
    qual_score, qual_match = score_qualification(full_text, profile)
    
    # 总分（最高 100 分）
    total_score = min(100, region_score + scale_score + scope_score + qual_score)
    
    # 生成原因
    reasons = []
    if region_score > 0:
        reasons.append(f"地域匹配：{matched_region}（+{region_score}分）")
    if scale_score > 0:
        reasons.append(f"规模匹配：{scale_match}（+{scale_score}分）")
        if tonnage:
            reasons.append(f"提取吨位：{tonnage}吨")
    if scope_score > 0:
        reasons.append(f"项目范围匹配：{scope_match}（+{scope_score}分）")
    if qual_score > 0:
        reasons.append(f"资质匹配：{qual_match}（+{qual_score}分）")
    
    if not reasons:
        reasons.append("未匹配到明显适配条件")
    
    # 风险提示
    risk_flags = []
    if region_score == 0:
        risk_flags.append("地域不在优先范围内")
    if scale_score == 0 and tonnage is not None:
        risk_flags.append(f"规模不在目标范围（当前：{tonnage}吨，目标：200-3000吨）")
    if scope_score < 10:
        risk_flags.append("项目类型或业务范围匹配度较低")
    if qual_score < 8:
        risk_flags.append("资质要求可能不完全匹配")
    
    return total_score, reasons, risk_flags


def is_clearly_mismatched(
    rule_score: int,
    rule_reasons: List[str],
    rule_risk_flags: List[str]
) -> Tuple[bool, str]:
    """
    判断规则是否明确判定为"不匹配"
    
    参数:
        rule_score: 规则评分
        rule_reasons: 规则评分原因
        rule_risk_flags: 规则风险提示
    
    返回:
        (is_mismatched, reason)
        is_mismatched: True 表示明确不匹配，False 表示不确定
        reason: 判断原因
    """
    # 明确不匹配的条件：
    # 1. 规则评分极低（< 10 分）
    # 2. 且至少有一个明确的负面风险提示
    
    if rule_score < 10 and rule_risk_flags:
        # 检查是否有明确的负面提示（不是"信息不足"类的）
        negative_flags = [
            "地域不在优先范围内",
            "规模不在目标范围",
            "项目类型或业务范围匹配度较低",
            "资质要求可能不完全匹配"
        ]
        if any(flag in rule_risk_flags for flag in negative_flags):
            return (True, f"规则评分极低（{rule_score}分）且存在明确负面风险提示")
    
    # 如果规则评分很低但原因明确（不是"未匹配到"这种模糊表述）
    if rule_score < 20:
        if "未匹配到明显适配条件" not in " ".join(rule_reasons):
            # 有具体的不匹配原因
            return (True, f"规则评分低（{rule_score}分）且有明确不匹配原因")
    
    return (False, "规则未明确判定为不匹配")

