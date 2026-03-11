"""vivo 校招招聘爬虫 - 北森系统"""
import asyncio
from typing import List, Dict
from playwright.async_api import async_playwright, Browser, Page
from datetime import datetime

from .base import BaseScraper, Job
from .registry import ScraperRegistry


@ScraperRegistry.register('vivo')
class VivoScraper(BaseScraper):
    """vivo 校招招聘系统爬虫（北森系统）"""

    @classmethod
    def get_scraper_type(cls) -> str:
        return 'vivo'

    def __init__(self, company_name: str, domain: str, **kwargs):
        super().__init__(company_name, domain, **kwargs)
        self.browser: Browser = None
        self.page: Page = None
        self._api_responses: List[Dict] = []
        self.path = kwargs.get('path', '/jobs')
        self._job_type = '校招'
        self.max_pages = kwargs.get('max_pages', 100)  # 默认最多爬 100 页

    async def _init_browser(self):
        """初始化浏览器"""
        self.progress("正在启动浏览器...")
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)
        self.page = await self.browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )

    async def _close_browser(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()

    async def scrape(self) -> List[Job]:
        """执行爬取"""
        await self._init_browser()

        # 设置 API 响应拦截器
        self._api_responses = []
        self._total_count = 0
        self._total_pages = 0
        self._current_page = 0

        async def handle_response(response):
            url = response.url
            # 北森系统职位列表 API
            if 'GetJobAdPageList' in url:
                try:
                    data = await response.json()
                    if data.get('Code') == 200 and 'Data' in data:
                        self._api_responses.append(data['Data'])
                        self._total_count = data.get('Count', 0)
                except:
                    pass

        self.page.on("response", handle_response)

        try:
            # 访问招聘页面
            self.progress(f"正在访问{self._job_type}页面...")
            url = f"https://{self.domain}{self.path}"
            await self.page.goto(url, timeout=60000)
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)

            # 检查是否获取到 API 数据
            if self._api_responses:
                self.progress(f"捕获到职位数据...")

                # 计算总页数（确保 _total_count 是整数）
                total_count = int(self._total_count) if self._total_count else 0
                self._total_pages = (total_count + 19) // 20  # 每页 20 条

                self.progress(f"检测到 {total_count} 个职位，共 {self._total_pages} 页")

                # 翻页爬取
                pages_to_crawl = min(self._total_pages, self.max_pages) if self.max_pages else self._total_pages
                if pages_to_crawl > 1:
                    for page_num in range(1, pages_to_crawl):
                        self.progress_with_eta(page_num + 1, pages_to_crawl, f"已获取 {len(self._api_responses) * 20} 职位")
                        await self._goto_page(page_num)
                        await asyncio.sleep(1)

                # 解析所有职位
                self.progress("正在处理职位数据...")
                jobs = self._parse_all_positions()

                self.done(len(jobs))
                return jobs
            else:
                self.progress("未捕获到 API 数据")
                self.done(0)
                return []

        finally:
            await self._close_browser()

    async def _goto_page(self, page_index: int):
        """翻到指定页（通过滚动触发）"""
        # 滚动页面触发下一页加载
        await self.page.evaluate(f"""() => {{
            window.scrollTo(0, document.body.scrollHeight);
        }}""")
        await asyncio.sleep(1)

    def _parse_all_positions(self) -> List[Job]:
        """解析所有职位数据"""
        all_positions = []
        seen_ids = set()

        for resp in self._api_responses:
            if isinstance(resp, list):
                for pos in resp:
                    pos_id = pos.get('JobAdId') or pos.get('Id')
                    if pos_id and pos_id not in seen_ids:
                        seen_ids.add(pos_id)
                        all_positions.append(pos)

        jobs = []
        for pos in all_positions:
            duty = pos.get('Duty', '')
            require = pos.get('Require', '')
            description = ""
            if duty:
                description += f"【职位描述】\n{duty}"
            if require:
                if description:
                    description += "\n\n"
                description += f"【任职要求】\n{require}"

            job = Job(
                title=pos.get('JobAdName', '') or pos.get('PositionName', ''),
                company=self.company_name,
                salary=pos.get('Salary', '') or '',
                location=', '.join(pos.get('LocNames', [])) if pos.get('LocNames') else '',
                job_type=self._job_type,
                description=description,
                url=f"https://{self.domain}/jobad/detail/{pos.get('JobAdId', '')}" if pos.get('JobAdId') else f"https://{self.domain}/jobs",
                published_date=pos.get('PostDate', '')[:10] if pos.get('PostDate') and len(pos.get('PostDate', '')) > 10 else ''
            )
            jobs.append(job)

        return jobs
