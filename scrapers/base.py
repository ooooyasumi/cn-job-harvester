from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List
import asyncio


@dataclass
class Job:
    """职位数据类"""
    title: str           # 职位名称
    company: str         # 公司名称
    salary: str          # 薪资范围
    location: str        # 工作地点
    job_type: str        # 全职/实习，社招/校招
    description: str     # 职位描述
    url: str             # 投递链接
    published_date: str  # 发布时间


class BaseScraper(ABC):
    """爬虫基类"""

    def __init__(self, company_name: str, domain: str):
        self.company_name = company_name
        self.domain = domain
        self.jobs: List[Job] = []

    @abstractmethod
    async def scrape(self) -> List[Job]:
        """执行爬取"""
        pass

    def get_job_url(self, job_id: str = "") -> str:
        """获取职位投递链接"""
        return f"https://{self.domain}/index/"
