"""爬虫基类 - 统一接口和进度显示"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Callable, Dict, Any
import time


@dataclass
class Job:
    """职位数据类"""
    title: str           # 职位名称
    company: str         # 公司名称
    salary: str          # 薪资范围
    location: str        # 工作地点
    job_type: str        # 社招/校招
    description: str     # 职位描述
    url: str             # 投递链接
    published_date: str  # 发布时间


class BaseScraper(ABC):
    """爬虫基类 - 统一接口和进度显示

    所有爬虫都应该继承此类并实现以下方法：
    - get_scraper_type(): 返回爬虫类型标识
    - scrape(): 执行爬取逻辑
    - get_job_url(): 生成职位链接

    使用 progress() 方法报告进度，会自动格式化输出。
    """

    def __init__(self, company_name: str, domain: str, **kwargs):
        """初始化爬虫

        Args:
            company_name: 公司名称
            domain: 招聘网站域名
            **kwargs: 额外参数
                - status_callback: 状态回调函数
                - max_pages: 最大爬取页数（可选，None 表示不限制）
        """
        self.company_name = company_name
        self.domain = domain
        self._status_callback: Optional[Callable] = kwargs.get('status_callback')
        self.max_pages: Optional[int] = kwargs.get('max_pages')
        self.jobs: List[Job] = []

        # 进度追踪（用于统一的进度显示）
        self._start_time: float = 0
        self._current: int = 0
        self._total: int = 0

    @classmethod
    @abstractmethod
    def get_scraper_type(cls) -> str:
        """返回爬虫类型标识

        Returns:
            爬虫类型字符串（如 'feishu', 'bytedance'）
        """
        pass

    @abstractmethod
    async def scrape(self) -> List[Job]:
        """执行爬取

        Returns:
            爬取到的职位列表
        """
        pass

    def progress(self, message: str, current: int = None, total: int = None):
        """报告进度（统一格式）

        Args:
            message: 状态消息
            current: 当前进度（可选）
            total: 总数（可选）

        示例:
            self.progress("正在启动浏览器...")
            self.progress("正在爬取第 5/100 页...", current=5, total=100)
        """
        if current is not None:
            self._current = current
        if total is not None:
            self._total = total

        if self._status_callback:
            self._status_callback(message)

    def progress_with_eta(self, current: int, total: int, extra_info: str = ""):
        """报告进度（带预计剩余时间）

        Args:
            current: 当前进度
            total: 总数
            extra_info: 额外信息（如已获取职位数）
        """
        self._current = current
        self._total = total

        if not self._status_callback:
            return

        # 计算进度和 ETA
        percent = (current / total * 100) if total > 0 else 0

        if self._start_time == 0:
            self._start_time = time.time()

        elapsed = time.time() - self._start_time
        if current > 1 and elapsed > 0:
            avg_time = elapsed / current
            remaining = (total - current) * avg_time
            eta = self._format_time(remaining)
        else:
            eta = "计算中..."

        # 构建消息
        msg = f"进度: {current}/{total} ({percent:.1f}%)"
        if extra_info:
            msg += f" | {extra_info}"
        msg += f" | 剩余: {eta}"

        self._status_callback(msg)

    def _format_time(self, seconds: float) -> str:
        """格式化时间"""
        if seconds < 60:
            return f"{int(seconds)}秒"
        elif seconds < 3600:
            return f"{int(seconds / 60)}分钟"
        else:
            hours = int(seconds / 3600)
            mins = int((seconds % 3600) / 60)
            return f"{hours}小时{mins}分钟"

    def done(self, count: int):
        """报告完成

        Args:
            count: 获取到的职位数量
        """
        self.progress(f"完成，共 {count} 个职位")

    def get_job_url(self, job_id: str = "") -> str:
        """获取职位投递链接"""
        return f"https://{self.domain}/index/"