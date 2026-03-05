"""腾讯招聘爬虫"""
import asyncio
from typing import List, Dict
from playwright.async_api import async_playwright, Browser, Page
from datetime import datetime

from .base import BaseScraper, Job
from .registry import ScraperRegistry


@ScraperRegistry.register('tencent')
class TencentScraper(BaseScraper):
    """腾讯招聘系统爬虫"""

    @classmethod
    def get_scraper_type(cls) -> str:
        return 'tencent'

    def __init__(self, company_name: str, domain: str, **kwargs):
        super().__init__(company_name, domain, **kwargs)
        self.browser: Browser = None
        self.page: Page = None
        self._api_responses: List[Dict] = []

    async def _init_browser(self):
        self.progress("正在启动浏览器...")
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)
        self.page = await self.browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )

    async def _close_browser(self):
        if self.browser:
            await self.browser.close()

    async def scrape(self) -> List[Job]:
        """执行爬取 - 根据域名判断爬取校招还是社招"""
        await self._init_browser()

        self._api_responses = []

        async def handle_response(response):
            url = response.url
            if "searchPosition" in url or "/post/Query" in url:
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type or "text/json" in content_type:
                    try:
                        data = await response.json()
                        self._api_responses.append({
                            'url': url,
                            'data': data,
                            'type': 'searchPosition' if 'searchPosition' in url else 'Query'
                        })
                    except:
                        pass

        self.page.on("response", handle_response)

        try:
            all_jobs = []

            # 根据域名判断爬取类型
            if 'join.qq.com' in self.domain:
                # 校招
                all_jobs = await self._crawl_campus()
            elif 'careers.tencent.com' in self.domain:
                # 社招
                all_jobs = await self._crawl_social()

            self.done(len(all_jobs))
            return all_jobs

        finally:
            await self._close_browser()

    async def _crawl_campus(self) -> List[Job]:
        """爬取校招 (join.qq.com)"""
        self.progress("正在访问校招页面...")
        await self.page.goto("https://join.qq.com/post.html", timeout=60000)
        await self.page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)

        # 获取总数
        self.progress("正在获取职位总数...")
        total_count = await self._get_campus_total_count()
        total_pages = (total_count + 99) // 100

        self.progress(f"检测到 {total_count} 个职位，{total_pages} 页")

        jobs = []
        for page_num in range(1, total_pages + 1):
            self.progress_with_eta(page_num, total_pages, f"已获 {len(jobs)} 职位")
            positions = await self._fetch_campus_page(page_num, 100)

            for pos in positions:
                jobs.append(Job(
                    title=pos.get('positionTitle', ''),
                    company=self.company_name,
                    salary='',
                    location=self._parse_cities(pos.get('workCities', '')),
                    job_type='校招',
                    description=f"职位 ID: {pos.get('postId', '')}\n事业群：{pos.get('bgs', '')}",
                    url=f"https://join.qq.com/post_detail.html?pid={pos.get('postId', '')}",
                    published_date=datetime.now().strftime('%Y-%m-%d')
                ))

            if page_num < total_pages:
                await asyncio.sleep(0.5)

        return jobs

    async def _crawl_social(self) -> List[Job]:
        """爬取社招 (careers.tencent.com)"""
        self.progress("正在访问社招页面...")
        await self.page.goto("https://careers.tencent.com/search.html", timeout=60000)
        await self.page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)

        # 从 API 响应获取总数
        total_count = 0
        for resp in self._api_responses:
            if resp['type'] == 'Query':
                data = resp['data']
                if data.get('Code') == 200:
                    total_count = data.get('Data', {}).get('Count', 0)
                    break

        total_pages = (total_count + 9) // 10
        max_pages = min(total_pages, self.max_pages) if self.max_pages else total_pages

        self.progress(f"检测到 {total_count} 个职位，计划爬取 {max_pages} 页")

        # 翻页
        for page_num in range(2, max_pages + 1):
            self.progress_with_eta(page_num, max_pages)
            await self._goto_page(page_num)
            await asyncio.sleep(2)

        # 解析
        jobs = []
        seen_ids = set()

        for resp in self._api_responses:
            if resp['type'] != 'Query':
                continue
            data = resp['data']
            if data.get('Code') != 200:
                continue

            for post in data.get('Data', {}).get('Posts', []):
                post_id = post.get('PostId', '')
                if post_id in seen_ids:
                    continue
                seen_ids.add(post_id)

                jobs.append(Job(
                    title=post.get('RecruitPostName', ''),
                    company=self.company_name,
                    salary='',
                    location=post.get('LocationName', ''),
                    job_type='社招',
                    description=post.get('Responsibility', ''),
                    url=post.get('PostURL', ''),
                    published_date=self._parse_date(post.get('LastUpdateTime', ''))
                ))

        return jobs

    async def _get_campus_total_count(self) -> int:
        result = await self.page.evaluate('''() => {
            return fetch('https://join.qq.com/api/v1/position/searchPosition', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    projectIdList: [],
                    projectMappingIdList: [1, 2, 104, 14, 20, 25, 5],
                    keyword: '',
                    bgList: [],
                    workCountryType: 0,
                    workCityList: [],
                    recruitCityList: [],
                    positionFidList: [],
                    pageIndex: 1,
                    pageSize: 1
                })
            }).then(r => r.json());
        }''')
        if result.get('status') == 0:
            return result.get('data', {}).get('count', 0)
        return 0

    async def _fetch_campus_page(self, page_num: int, page_size: int) -> List[Dict]:
        result = await self.page.evaluate('''([pageNum, pageSize]) => {
            return fetch('https://join.qq.com/api/v1/position/searchPosition', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    projectIdList: [],
                    projectMappingIdList: [1, 2, 104, 14, 20, 25, 5],
                    keyword: '',
                    bgList: [],
                    workCountryType: 0,
                    workCityList: [],
                    recruitCityList: [],
                    positionFidList: [],
                    pageIndex: pageNum,
                    pageSize: pageSize
                })
            }).then(r => r.json());
        }''', [page_num, page_size])
        if result.get('status') == 0:
            return result.get('data', {}).get('positionList', [])
        return []

    def _parse_cities(self, cities_str: str) -> str:
        if not cities_str:
            return ''
        cities = cities_str.strip().split(' ')
        return cities[0] if cities else ''

    def _parse_date(self, date_str: str) -> str:
        if not date_str:
            return ''
        return date_str.replace('年', '-').replace('月', '-').replace('日', '')

    async def _goto_page(self, page_num: int):
        await self.page.evaluate("""(pageNum) => {
            const pageItems = document.querySelectorAll('[class*="page"]');
            for (let item of pageItems) {
                const text = item.innerText.trim();
                if (text === String(pageNum)) {
                    item.click();
                    return true;
                }
            }
            const buttons = Array.from(document.querySelectorAll('button, a, [role="button"]'));
            for (let btn of buttons) {
                const text = btn.innerText.trim();
                if (text === '下一页' || text === '>' || text === '»') {
                    if (!btn.disabled) {
                        btn.click();
                        return true;
                    }
                }
            }
            return false;
        }""", page_num)