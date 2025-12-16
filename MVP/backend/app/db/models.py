"""
数据库模型
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, Column, String, Text, DateTime, JSON, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import os

Base = declarative_base()


class Notice(Base):
    """招标公告表"""
    __tablename__ = 'notices'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False, comment='公告标题')
    url = Column(String(1000), comment='公告链接（可为空）')
    source_item_id = Column(String(200), comment='源站项目ID')
    canonical_key = Column(String(300), unique=True, nullable=False, comment='规范化唯一键（用于去重）')
    published_at = Column(DateTime, comment='发布日期')
    raw_text = Column(Text, comment='公告正文')
    analysis_json = Column(JSON, comment='AI 分析结果')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'title': self.title,
            'url': self.url,
            'source_item_id': self.source_item_id,
            'canonical_key': self.canonical_key,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'raw_text': self.raw_text,
            'analysis_json': self.analysis_json,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


# 数据库连接
_db_url = os.getenv('DATABASE_URL', 'sqlite:///./tender_notices.db')
_engine = None
_SessionLocal = None


def init_db(db_url: Optional[str] = None):
    """
    初始化数据库
    
    参数:
        db_url: 数据库 URL，默认使用环境变量或 SQLite
    """
    global _engine, _SessionLocal
    
    if db_url:
        db_url_to_use = db_url
    else:
        db_url_to_use = _db_url
    
    _engine = create_engine(db_url_to_use, echo=False)
    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    
    print(f"[DB] 数据库初始化完成: {db_url_to_use}")


def get_db_session() -> Session:
    """
    获取数据库会话
    
    返回:
        数据库会话
    """
    if _SessionLocal is None:
        init_db()
    
    return _SessionLocal()

