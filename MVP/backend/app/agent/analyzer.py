"""
AI Agent 核心分析模块
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional

from .schema import TenderAnalysisResult, create_fallback_result
from .score_rules import rule_score, load_company_profile
from .prompts import build_analysis_prompt
from .ollama_client import call_ollama, parse_json_response


async def analyze_notice(
    title: str,
    url: str,
    raw_text: str,
    extracted_fields: Optional[Dict] = None
) -> Dict:
    """
    分析招标公告
    
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
        # 1. 加载公司画像
        profile = load_company_profile()
        
        # 2. 规则评分
        rule_score_value, rule_reasons, rule_risk_flags = rule_score(
            raw_text, extracted_fields
        )
        
        # 3. 构造 Prompt
        prompt = build_analysis_prompt(
            company_profile=profile,
            rule_score=rule_score_value,
            rule_reasons=rule_reasons,
            rule_risk_flags=rule_risk_flags,
            title=title,
            raw_text=raw_text,
            extracted_fields=extracted_fields
        )
        
        # 4. 调用 Ollama
        try:
            response_text = await call_ollama(prompt)
        except Exception as e:
            # Ollama 调用失败，使用 fallback
            print(f"Ollama 调用失败: {e}")
            result = create_fallback_result()
            result["summary"] = f"AI 分析失败: {str(e)}。规则评分: {rule_score_value}/100"
            result["reasons"] = rule_reasons
            result["risk_flags"] = rule_risk_flags
            return result
        
        # 5. 解析 JSON 响应
        parsed_json = parse_json_response(response_text)
        
        if parsed_json is None:
            # JSON 解析失败，使用 fallback
            print(f"JSON 解析失败，原始输出: {response_text[:300]}")
            result = create_fallback_result()
            result["summary"] = f"AI 输出格式异常。规则评分: {rule_score_value}/100。原始输出: {response_text[:300]}"
            result["reasons"] = rule_reasons
            result["risk_flags"] = rule_risk_flags
            return result
        
        # 6. 校验 Schema
        try:
            # 使用 Pydantic 校验
            validated_result = TenderAnalysisResult(**parsed_json)
            result_dict = validated_result.model_dump()
        except Exception as e:
            # Schema 校验失败，使用 fallback 但保留部分信息
            print(f"Schema 校验失败: {e}")
            result = create_fallback_result()
            result["summary"] = f"AI 输出格式校验失败: {str(e)}。规则评分: {rule_score_value}/100"
            result["reasons"] = rule_reasons
            result["risk_flags"] = rule_risk_flags
            
            # 尝试提取部分有效信息
            if "summary" in parsed_json:
                result["summary"] = str(parsed_json["summary"])[:300]
            if "fit_score" in parsed_json:
                try:
                    result["fit_score"] = int(parsed_json["fit_score"])
                    if result["fit_score"] >= 70:
                        result["fit_label"] = "RECOMMEND"
                    elif result["fit_score"] >= 40:
                        result["fit_label"] = "REVIEW"
                    else:
                        result["fit_label"] = "SKIP"
                except:
                    pass
            
            return result
        
        # 7. 补充元数据
        result_dict["_meta"] = {
            "url": url,
            "title": title,
            "rule_score": rule_score_value,
            "analysis_timestamp": None  # 可以由调用方补充
        }
        
        return result_dict
        
    except Exception as e:
        # 任何未预期的错误，返回 fallback
        print(f"分析过程出错: {e}")
        result = create_fallback_result()
        result["summary"] = f"分析过程出错: {str(e)}"
        result["reasons"] = ["系统错误，需要人工审核"]
        result["risk_flags"] = ["分析流程异常"]
        return result

