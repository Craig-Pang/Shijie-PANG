"""
定义 AI agent 输出的 Pydantic Schema
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Literal, Optional


class KeyFields(BaseModel):
    """关键字段提取"""
    location: str = Field(default="", description="项目地点")
    scope: str = Field(default="", description="项目范围/内容")
    deadline: str = Field(default="", description="投标截止时间")
    tonnage: str = Field(default="", description="钢结构吨位")
    qualification: str = Field(default="", description="所需资质要求")


class TenderAnalysisResult(BaseModel):
    """招标分析结果"""
    decision_state: Literal["RECOMMEND", "REVIEW", "SKIP", "UNKNOWN"] = Field(
        description="决策状态：RECOMMEND(明确匹配)、REVIEW(需复核)、SKIP(明确不匹配)、UNKNOWN(信息不足)"
    )
    fit_label: Literal["RECOMMEND", "REVIEW", "SKIP", "UNKNOWN"] = Field(
        description="推荐标签（兼容 decision_state）"
    )
    fit_score: Optional[int] = Field(
        default=None, ge=0, le=100, description="适配度评分 0-100（UNKNOWN 时为 null）"
    )
    region_match: Literal["HIGH", "MED", "LOW", "UNKNOWN"] = Field(description="地域匹配度")
    scope_match: Literal["HIGH", "MED", "LOW", "UNKNOWN"] = Field(description="范围匹配度")
    scale_match: Literal["HIGH", "MED", "LOW", "UNKNOWN"] = Field(description="规模匹配度")
    qualification_match: Literal["HIGH", "MED", "LOW", "UNKNOWN"] = Field(description="资质匹配度")
    summary: str = Field(default="", description="分析摘要")
    reasons: List[str] = Field(default_factory=list, description="推荐/不推荐原因")
    risk_flags: List[str] = Field(default_factory=list, description="风险提示")
    key_fields: KeyFields = Field(default_factory=KeyFields, description="关键字段")


def create_fallback_result(decision_source: str = "FALLBACK") -> Dict:
    """创建 fallback 结果（当 LLM 输出无效时）"""
    return {
        "decision_state": "REVIEW",
        "fit_label": "REVIEW",
        "fit_score": 50,
        "region_match": "UNKNOWN",
        "scope_match": "UNKNOWN",
        "scale_match": "UNKNOWN",
        "qualification_match": "UNKNOWN",
        "summary": "AI 分析失败，需要人工审核",
        "reasons": ["AI 模型输出格式异常，已回退到人工审核模式"],
        "risk_flags": ["需要人工确认项目适配度"],
        "key_fields": {
            "location": "",
            "scope": "",
            "deadline": "",
            "tonnage": "",
            "qualification": ""
        },
        "_meta": {
            "decision_source": decision_source
        }
    }

