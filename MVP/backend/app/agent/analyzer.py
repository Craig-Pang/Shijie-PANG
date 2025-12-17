"""
AI Agent 核心分析模块
重构后：引入输入质量门控，明确责任边界
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional

from .schema import TenderAnalysisResult, create_fallback_result
from .score_rules import rule_score, load_company_profile, is_clearly_mismatched
from .input_quality_gate import check_input_quality, create_insufficient_info_result
from .prompts import build_analysis_prompt
from .ollama_client import call_ollama, parse_json_response


def normalize_fit_label(label: str) -> str:
    """
    规范化 fit_label，处理非法值
    
    参数:
        label: 原始 label
    
    返回:
        规范化后的 label（RECOMMEND/REVIEW/SKIP/UNKNOWN）
    """
    label_upper = str(label).upper().strip()
    
    valid_labels = ["RECOMMEND", "REVIEW", "SKIP", "UNKNOWN"]
    
    if label_upper in valid_labels:
        return label_upper
    
    # 处理非法值：自动回退
    if label_upper in ["-", "", "NULL", "NONE", "N/A"]:
        return "UNKNOWN"
    
    # 其他非法值回退为 REVIEW
    print(f"[WARNING] 非法 fit_label: {label}，回退为 REVIEW")
    return "REVIEW"


def check_consistency(result: Dict, rule_score: int, rule_is_mismatched: bool) -> Dict:
    """
    一致性校验和修正
    
    参数:
        result: LLM 输出结果
        rule_score: 规则评分
        rule_is_mismatched: 规则是否明确不匹配
    
    返回:
        修正后的结果
    """
    fit_score = result.get("fit_score")
    fit_label = result.get("fit_label", "")
    summary = result.get("summary", "").lower()
    
    # 修正 1: fit_label 规范化
    result["fit_label"] = normalize_fit_label(fit_label)
    
    # 修正 2: 如果规则明确不匹配，LLM 不得输出 RECOMMEND
    if rule_is_mismatched and result["fit_label"] == "RECOMMEND":
        print(f"[CONSISTENCY] 规则明确不匹配，但 LLM 输出 RECOMMEND，强制降级为 SKIP")
        result["fit_label"] = "SKIP"
        result["decision_state"] = "SKIP"
        if fit_score and fit_score > 40:
            result["fit_score"] = 30  # 强制降低分数
    
    # 修正 3: 如果 fit_score >= 80，但 summary 中出现"信息不足/不明确"，强制降级为 REVIEW
    if fit_score and fit_score >= 80:
        insufficient_keywords = ["信息不足", "信息不明确", "未明确", "无法确定", "无法判断", "不清楚"]
        if any(kw in summary for kw in insufficient_keywords):
            print(f"[CONSISTENCY] 高分但摘要显示信息不足，强制降级为 REVIEW")
            result["fit_label"] = "REVIEW"
            result["decision_state"] = "REVIEW"
            result["fit_score"] = min(60, fit_score - 20)  # 降低分数
    
    # 修正 4: 确保 decision_state 与 fit_label 一致
    if "decision_state" not in result:
        result["decision_state"] = result["fit_label"]
    elif result["decision_state"] != result["fit_label"]:
        # 以 fit_label 为准
        result["decision_state"] = result["fit_label"]
    
    return result


async def analyze_notice(
    title: str,
    url: str,
    raw_text: str,
    extracted_fields: Optional[Dict] = None
) -> Dict:
    """
    分析招标公告（重构后：引入质量门控和责任边界）
    
    责任分配：
    - 规则引擎：负责事实判断（是否明显不匹配）
    - 质量门控：判断输入是否足够进行分析
    - LLM：只在输入质量足够且规则未明确不匹配时调用，负责语义补充
    
    参数:
        title: 招标标题
        url: 招标链接
        raw_text: 招标正文
        extracted_fields: 已提取的字段（可选）
    
    返回:
        分析结果字典（可直接存入数据库）
    """
    if extracted_fields is None:
        extracted_fields = {}
    
    try:
        # ========== 阶段 1: 输入质量门控 ==========
        print(f"[QUALITY_GATE] 检查输入质量...")
        input_quality, quality_info = check_input_quality(raw_text, title, extracted_fields)
        
        if input_quality == "INSUFFICIENT":
            print(f"[QUALITY_GATE] ❌ 输入质量不足，拒绝分析")
            print(f"[QUALITY_GATE] 原因: {quality_info['reasons']}")
            
            # 仍然执行规则评分（用于记录）
            rule_score_value, rule_reasons, rule_risk_flags = rule_score(
                raw_text, extracted_fields
            )
            
            # 返回"信息不足"结果
            result = create_insufficient_info_result(
                rule_score_value, rule_reasons, quality_info
            )
            result["_meta"]["input_quality"] = "INSUFFICIENT"
            result["_meta"]["decision_source"] = "QUALITY_GATE"
            result["_meta"]["url"] = url
            result["_meta"]["title"] = title
            result["_meta"]["rule_score"] = rule_score_value
            
            return result
        
        print(f"[QUALITY_GATE] ✅ 输入质量良好，继续分析")
        print(f"[QUALITY_GATE] 关键字段数量: {quality_info['key_fields_count']}")
        
        # ========== 阶段 2: 规则评分（事实判断） ==========
        print(f"[RULE_ENGINE] 执行规则评分...")
        rule_score_value, rule_reasons, rule_risk_flags = rule_score(
            raw_text, extracted_fields
        )
        print(f"[RULE_ENGINE] 规则评分: {rule_score_value}/100")
        print(f"[RULE_ENGINE] 原因: {rule_reasons}")
        
        # 判断是否明确不匹配
        is_mismatched, mismatch_reason = is_clearly_mismatched(
            rule_score_value, rule_reasons, rule_risk_flags
        )
        
        if is_mismatched:
            print(f"[RULE_ENGINE] ⚠️  规则明确判定为不匹配: {mismatch_reason}")
            print(f"[RULE_ENGINE] 不调用 LLM，直接返回 SKIP")
            
            # 规则明确不匹配，直接返回，不调用 LLM
            result = {
                "decision_state": "SKIP",
                "fit_label": "SKIP",
                "fit_score": max(0, min(30, rule_score_value)),  # 明确不匹配，分数上限 30
                "region_match": "LOW" if rule_score_value < 10 else "UNKNOWN",
                "scope_match": "LOW" if rule_score_value < 10 else "UNKNOWN",
                "scale_match": "LOW" if rule_score_value < 10 else "UNKNOWN",
                "qualification_match": "LOW" if rule_score_value < 10 else "UNKNOWN",
                "summary": f"规则引擎明确判定为不匹配。{mismatch_reason}。规则评分：{rule_score_value}/100。",
                "reasons": rule_reasons,
                "risk_flags": rule_risk_flags,
                "key_fields": {
                    "location": extracted_fields.get("location", ""),
                    "scope": extracted_fields.get("scope", ""),
                    "deadline": extracted_fields.get("deadline", ""),
                    "tonnage": extracted_fields.get("tonnage", ""),
                    "qualification": extracted_fields.get("qualification", "")
                },
                "_meta": {
                    "input_quality": "GOOD",
                    "decision_source": "RULE",
                    "rule_score": rule_score_value,
                    "url": url,
                    "title": title
                }
            }
            return result
        
        print(f"[RULE_ENGINE] ✅ 规则未明确不匹配，继续调用 LLM 进行语义补充")
        
        # ========== 阶段 3: LLM 语义补充（仅在质量足够且规则未明确不匹配时） ==========
        print(f"[LLM] 调用 LLM 进行语义补充...")
        
        # 加载公司画像
        profile = load_company_profile()
        
        # 构造 Prompt（明确 LLM 职责：语义补充，不是替代事实判断）
        prompt = build_analysis_prompt(
            company_profile=profile,
            rule_score=rule_score_value,
            rule_reasons=rule_reasons,
            rule_risk_flags=rule_risk_flags,
            title=title,
            raw_text=raw_text,
            extracted_fields=extracted_fields
        )
        
        # 调用 Ollama
        try:
            response_text = await call_ollama(prompt)
            print(f"[LLM] ✅ LLM 调用成功")
        except Exception as e:
            print(f"[LLM] ❌ Ollama 调用失败: {e}")
            result = create_fallback_result("LLM_ERROR")
            result["summary"] = f"AI 分析失败: {str(e)}。规则评分: {rule_score_value}/100"
            result["reasons"] = rule_reasons
            result["risk_flags"] = rule_risk_flags
            result["_meta"]["input_quality"] = "GOOD"
            result["_meta"]["rule_score"] = rule_score_value
            result["_meta"]["url"] = url
            result["_meta"]["title"] = title
            return result
        
        # 解析 JSON 响应
        parsed_json = parse_json_response(response_text)
        
        if parsed_json is None:
            print(f"[LLM] ❌ JSON 解析失败")
            result = create_fallback_result("LLM_PARSE_ERROR")
            result["summary"] = f"AI 输出格式异常。规则评分: {rule_score_value}/100。原始输出: {response_text[:300]}"
            result["reasons"] = rule_reasons
            result["risk_flags"] = rule_risk_flags
            result["_meta"]["input_quality"] = "GOOD"
            result["_meta"]["rule_score"] = rule_score_value
            result["_meta"]["url"] = url
            result["_meta"]["title"] = title
            return result
        
        # ========== 阶段 4: Schema 校验和一致性修正 ==========
        print(f"[VALIDATION] 执行 Schema 校验和一致性检查...")
        
        try:
            # 确保 fit_score 在有效范围内（如果存在）
            if 'fit_score' in parsed_json and parsed_json['fit_score'] is not None:
                parsed_json['fit_score'] = max(0, min(100, int(parsed_json['fit_score'])))
            
            # 规范化 fit_label
            if 'fit_label' in parsed_json:
                parsed_json['fit_label'] = normalize_fit_label(parsed_json['fit_label'])
            
            # 确保 decision_state 存在
            if 'decision_state' not in parsed_json:
                parsed_json['decision_state'] = parsed_json.get('fit_label', 'REVIEW')
            
            # 使用 Pydantic 校验
            validated_result = TenderAnalysisResult(**parsed_json)
            result_dict = validated_result.model_dump()
            
            # 一致性校验和修正
            result_dict = check_consistency(result_dict, rule_score_value, is_mismatched)
            
            print(f"[VALIDATION] ✅ Schema 校验通过")
            
        except Exception as e:
            print(f"[VALIDATION] ❌ Schema 校验失败: {e}")
            result = create_fallback_result("SCHEMA_ERROR")
            result["summary"] = f"AI 输出格式校验失败: {str(e)}。规则评分: {rule_score_value}/100"
            result["reasons"] = rule_reasons
            result["risk_flags"] = rule_risk_flags
            
            # 尝试提取部分有效信息
            if "summary" in parsed_json:
                result["summary"] = str(parsed_json["summary"])[:300]
            if "fit_score" in parsed_json and parsed_json["fit_score"] is not None:
                try:
                    score = max(0, min(100, int(parsed_json["fit_score"])))
                    result["fit_score"] = score
                    result["fit_label"] = normalize_fit_label(parsed_json.get("fit_label", "REVIEW"))
                    result["decision_state"] = result["fit_label"]
                except:
                    pass
            
            result["_meta"]["input_quality"] = "GOOD"
            result["_meta"]["rule_score"] = rule_score_value
            result["_meta"]["url"] = url
            result["_meta"]["title"] = title
            return result
        
        # ========== 阶段 5: 补充元数据 ==========
        result_dict["_meta"] = {
            "url": url,
            "title": title,
            "rule_score": rule_score_value,
            "input_quality": "GOOD",
            "decision_source": "LLM",
            "analysis_timestamp": None
        }
        
        print(f"[ANALYSIS] ✅ 分析完成")
        print(f"[ANALYSIS] 决策状态: {result_dict.get('decision_state')}")
        print(f"[ANALYSIS] 评分: {result_dict.get('fit_score')}")
        print(f"[ANALYSIS] 标签: {result_dict.get('fit_label')}")
        
        return result_dict
        
    except Exception as e:
        # 任何未预期的错误
        print(f"[ERROR] 分析过程出错: {e}")
        import traceback
        traceback.print_exc()
        
        result = create_fallback_result("SYSTEM_ERROR")
        result["summary"] = f"分析过程出错: {str(e)}"
        result["reasons"] = ["系统错误，需要人工审核"]
        result["risk_flags"] = ["分析流程异常"]
        result["_meta"]["input_quality"] = "UNKNOWN"
        result["_meta"]["decision_source"] = "FALLBACK"
        return result
