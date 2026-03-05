"""爬虫注册器 - 支持动态注册和获取爬虫"""
from typing import Dict, List, Optional, Type


class ScraperRegistry:
    """爬虫注册器 - 支持动态注册和获取爬虫

    使用方法:
        # 注册爬虫
        @ScraperRegistry.register('feishu')
        class FeishuScraper(BaseScraper):
            ...

        # 获取爬虫类
        scraper_class = ScraperRegistry.get('feishu')

        # 列出所有已注册的爬虫
        types = ScraperRegistry.list()
    """

    _scrapers: Dict[str, Type] = {}

    @classmethod
    def register(cls, scraper_type: str):
        """装饰器：注册爬虫类

        Args:
            scraper_type: 爬虫类型标识符（如 'feishu', 'bytedance'）

        Returns:
            装饰器函数
        """
        def decorator(scraper_class: Type):
            cls._scrapers[scraper_type] = scraper_class
            return scraper_class
        return decorator

    @classmethod
    def get(cls, scraper_type: str) -> Optional[Type]:
        """获取爬虫类

        Args:
            scraper_type: 爬虫类型标识符

        Returns:
            爬虫类，如果不存在则返回 None
        """
        return cls._scrapers.get(scraper_type)

    @classmethod
    def list(cls) -> List[str]:
        """列出所有已注册的爬虫类型

        Returns:
            已注册的爬虫类型列表
        """
        return list(cls._scrapers.keys())

    @classmethod
    def exists(cls, scraper_type: str) -> bool:
        """检查爬虫类型是否已注册

        Args:
            scraper_type: 爬虫类型标识符

        Returns:
            是否已注册
        """
        return scraper_type in cls._scrapers