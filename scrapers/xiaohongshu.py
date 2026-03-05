"""小红书招聘爬虫"""
import asyncio
from typing import List, Dict
from playwright.async_api import async_playwright, Browser, Page
from datetime import datetime

from .base import BaseScraper, Job
from .registry import ScraperRegistry


@ScraperRegistry.register('xiaohongshu')
class XiaoHongShuScraper(BaseScraper):
    """小红书招聘系统爬虫"""

    @classmethod
    def get_scraper_type(cls) -> str:
        return 'xiaohongshu'

    def __init__(self, company_name: str, domain: str, **kwargs):
        super().__init__(company_name, domain, **kwargs)
        self.browser: Browser = None
        self.page: Page = None
        self._api_responses: List[Dict] = []
        # 获取路径参数，默认为校招
        self.path = kwargs.get('path', '/campus/position')
        # 根据路径确定类型
        self._job_type = '社招' if '/social' in self.path else '校招'

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

        async def handle_response(response):
            url = response.url
            # 拦截职位查询 API
            if 'pageQueryPosition' in url:
                try:
                    data = await response.json()
                    if data.get('success') and 'data' in data:
                        self._api_responses.append(data['data'])
                except:
                    pass

        self.page.on("response", handle_response)

        try:
            # 访问招聘页面（校招或社招）
            self.progress(f"正在访问{self._job_type}页面...")
            url = f"https://{self.domain}{self.path}"
            await self.page.goto(url, timeout=60000)
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)

            # 检查是否获取到 API 数据
            if self._api_responses:
                self.progress(f"捕获到职位数据...")

                # 获取总数和翻页爬取
                first_data = self._api_responses[0]
                total = first_data.get('total', 0)
                total_pages = first_data.get('totalPage', 1)

                self.progress(f"检测到 {total} 个职位，共 {total_pages} 页")

                # 翻页爬取
                if total_pages > 1:
                    for page_num in range(2, total_pages + 1):
                        self.progress_with_eta(page_num, total_pages, f"已获 {len(self._api_responses) * 10} 职位")
                        await self._goto_page(page_num)
                        await asyncio.sleep(1)

                # 解析所有职位
                self.progress("正在处理职位数据...")
                jobs = self._parse_all_positions()

                self.done(len(jobs))
                return jobs
            else:
                self.progress("未捕获到 API 数据，尝试从页面提取...")
                jobs = await self._extract_from_page()
                self.done(len(jobs))
                return jobs

        finally:
            await self._close_browser()

    async def _goto_page(self, page_num: int):
        """翻到指定页"""
        clicked = await self.page.evaluate('''(pageNum) => {
            const pageItems = document.querySelectorAll('[class*="page"], [class*="pagination"]');
            for (let item of pageItems) {
                const text = item.innerText || item.textContent;
                if (text.trim() === String(pageNum)) {
                    item.click();
                    return true;
                }
            }
            const buttons = document.querySelectorAll('button, [role="button"], a');
            for (let btn of buttons) {
                const text = btn.innerText || btn.textContent;
                if (text.includes('下一页') || text.includes('>')) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }''', page_num)

        if clicked:
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(1)

    def _parse_all_positions(self) -> List[Job]:
        """解析所有职位数据"""
        all_positions = []
        seen_ids = set()

        for resp in self._api_responses:
            positions = resp.get('list', [])
            for pos in positions:
                pos_id = pos.get('positionId')
                if pos_id and pos_id not in seen_ids:
                    seen_ids.add(pos_id)
                    all_positions.append(pos)

        jobs = []
        for pos in all_positions:
            duty = pos.get('duty', '')
            qualification = pos.get('qualification', '')
            description = ""
            if duty:
                description += f"【职位描述】\n{duty}"
            if qualification:
                if description:
                    description += "\n\n"
                description += f"【任职要求】\n{qualification}"

            job = Job(
                title=pos.get('positionName', ''),
                company=self.company_name,
                salary='',
                location=pos.get('workplace', ''),
                job_type=self._job_type,  # 根据路径使用校招或社招
                description=description,
                url=f"https://{self.domain}{self.path}/detail/{pos.get('positionId', '')}",
                published_date=pos.get('publishTime', '')
            )
            jobs.append(job)

        return jobs

    async def _extract_from_page(self) -> List[Job]:
        """从页面直接提取（备用方案）"""
        raw_data = await self.page.evaluate('''() => {
            const jobs = [];
            const cards = document.querySelectorAll('[class*="job"], [class*="position"], [class*="card"]');
            cards.forEach(card => {
                const text = card.innerText || '';
                const lines = text.split('\\n').filter(l => l.trim());
                if (lines.length >= 2) {
                    jobs.push({ title: lines[0], raw: text });
                }
            });
            return { jobs };
        }''')

        jobs = []
        for item in raw_data.get('jobs', []):
            title = item.get('title', '')
            if title and len(title) > 2:
                jobs.append(Job(
                    title=title,
                    company=self.company_name,
                    salary='',
                    location='',
                    job_type=self._job_type,
                    description=item.get('raw', ''),
                    url=f"https://{self.domain}{self.path}",
                    published_date=datetime.now().strftime('%Y-%m-%d')
                ))
        return jobs