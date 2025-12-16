"""
数据库操作
"""

from datetime import datetime
from typing import Optional, Dict
from sqlalchemy.orm import Session

from .models import Notice, get_db_session


def save_notice(
    title: str,
    url: str,
    raw_text: str = "",
    published_at: Optional[datetime] = None,
    analysis_json: Optional[Dict] = None,
    session: Optional[Session] = None
) -> Notice:
    """
    保存或更新公告
    
    参数:
        title: 标题
        url: URL
        raw_text: 正文
        published_at: 发布日期
        analysis_json: 分析结果
        session: 数据库会话（可选）
    
    返回:
        Notice 对象
    """
    if session is None:
        session = get_db_session()
        should_close = True
    else:
        should_close = False
    
    try:
        # 查找是否已存在
        notice = session.query(Notice).filter(Notice.url == url).first()
        
        if notice:
            # 更新
            notice.title = title
            notice.raw_text = raw_text
            if published_at:
                notice.published_at = published_at
            if analysis_json:
                notice.analysis_json = analysis_json
            notice.updated_at = datetime.now()
            print(f"[DB] 更新公告: {title[:50]}...")
        else:
            # 新建
            notice = Notice(
                title=title,
                url=url,
                raw_text=raw_text,
                published_at=published_at,
                analysis_json=analysis_json
            )
            session.add(notice)
            print(f"[DB] 新建公告: {title[:50]}...")
        
        session.commit()
        return notice
    except Exception as e:
        session.rollback()
        print(f"[DB] 保存失败: {e}")
        raise
    finally:
        if should_close:
            session.close()


def get_notice_by_url(url: str, session: Optional[Session] = None) -> Optional[Notice]:
    """
    根据 URL 获取公告
    
    参数:
        url: URL
        session: 数据库会话（可选）
    
    返回:
        Notice 对象或 None
    """
    if session is None:
        session = get_db_session()
        should_close = True
    else:
        should_close = False
    
    try:
        notice = session.query(Notice).filter(Notice.url == url).first()
        return notice
    finally:
        if should_close:
            session.close()

