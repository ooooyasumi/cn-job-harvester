"""JobHarvester - 招聘数据爬取工具

使用注册器模式管理爬虫，支持动态扩展。
"""
from .base import Job, BaseScraper
from .registry import ScraperRegistry

# 自动导入所有爬虫模块（触发注册）
from . import feishu, bytedance, tencent

__all__ = ['Job', 'BaseScraper', 'ScraperRegistry']