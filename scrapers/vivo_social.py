"""vivo 社招招聘爬虫"""
import asyncio
from typing import List, Dict
from playwright.async_api import async_playwright, Browser, Page
from datetime import datetime

from .base import BaseScraper, Job
from .registry import ScraperRegistry


@ScraperRegistry.register('vivo_social')
class VivoSocialScraper(BaseScraper):
    """vivo 社招招聘系统爬虫"""

    @classmethod
    def get_scraper_type(cls) -> str:
        return 'vivo_social'

    def __init__(self, company_name: str, domain: str, **kwargs):
        super().__init__(company_name, domain, **kwargs)
        self.browser: Browser = None
        self.page: Page = None
        self._api_responses: List[Dict] = []
        self.path = kwargs.get('path', '/jobs')
        self._job_type = '社招'
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
        self._total = 0
        self._page_count = 0
        self._current_page = 0

        async def handle_response(response):
            url = response.url
            # vivo 社招职位列表 API
            if '/portal/page' in url:
                try:
                    data = await response.json()
                    if data.get('code') == 0 and 'data' in data:
                        self._api_responses.append(data['data'])
                        meta = data.get('meta', {})
                        self._total = meta.get('total', 0)
                        self._page_count = meta.get('page_count', 0)
                        self._current_page = meta.get('page', 0)
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
                self.progress(f"检测到 {self._total} 个职位，共 {self._page_count} 页")

                # 翻页爬取（确保 max_pages 有默认值）
                max_pages = self.max_pages if self.max_pages else self._page_count
                pages_to_crawl = min(self._page_count, max_pages)
                if pages_to_crawl > 1:
                    for page_num in range(2, pages_to_crawl + 1):
                        self.progress_with_eta(page_num, pages_to_crawl, f"已获取 {len(self._api_responses) * 10} 职位")
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

    async def _goto_page(self, page_num: int):
        """翻到指定页 - 通过点击页码按钮"""
        # 使用 JavaScript 触发翻页请求
        clicked = await self.page.evaluate(f"""() => {{
            // 查找所有按钮和列表项
            const allElements = document.querySelectorAll('*');
            for (let el of allElements) {{
                const text = (el.innerText || el.textContent).trim();
                // 精确匹配页码数字
                if (text === String({page_num})) {{
                    // 检查是否是可点击元素或分页元素
                    const parent = el.closest('li, button, [role="button"], [class*="page"], [class*="Pagination"]');
                    if (parent) {{
                        parent.click();
                        return true;
                    }}
                    el.click();
                    return true;
                }}
            }}
            return false;
        }}""")

        if clicked:
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(1)

    def _parse_all_positions(self) -> List[Job]:
        """解析所有职位数据"""
        all_positions = []
        seen_ids = set()

        for resp in self._api_responses:
            if isinstance(resp, list):
                for pos in resp:
                    pos_id = pos.get('job_id')
                    if pos_id and pos_id not in seen_ids:
                        seen_ids.add(pos_id)
                        all_positions.append(pos)

        jobs = []
        for pos in all_positions:
            job_desc = pos.get('job_desc', '')
            description = job_desc if job_desc else ''

            # 获取地点列表
            location_list = pos.get('job_location_list', [])
            locations = []
            for loc in location_list:
                city = loc.get('city', '')
                if city:
                    locations.append(city)

            job = Job(
                title=pos.get('job_title', ''),
                company=self.company_name,
                salary='',  # 社招通常面议
                location=', '.join(locations) if locations else '',
                job_type=self._job_type,
                description=description,
                url=f"https://{self.domain}/job/{pos.get('job_id', '')}" if pos.get('job_id') else f"https://{self.domain}/jobs",
                published_date=''
            )
            jobs.append(job)

        return jobs
