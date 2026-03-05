"""字节跳动招聘爬虫"""
import asyncio
from typing import List, Dict
from playwright.async_api import async_playwright, Browser, Page
from datetime import datetime
import time

from .base import BaseScraper, Job
from .registry import ScraperRegistry


@ScraperRegistry.register('bytedance')
class ByteDanceScraper(BaseScraper):
    """字节跳动招聘系统爬虫"""

    PAGE_LOAD_TIMEOUT = 30000
    CLICK_DELAY = 0.3

    @classmethod
    def get_scraper_type(cls) -> str:
        return 'bytedance'

    def __init__(self, company_name: str, domain: str, **kwargs):
        super().__init__(company_name, domain, **kwargs)
        self.browser: Browser = None
        self.page: Page = None
        self._api_responses: List[Dict] = []

    async def _init_browser(self):
        """初始化浏览器"""
        self.progress("正在启动浏览器...")
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)
        self.page = await self.browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )

        # 拦截不必要的请求
        async def route_request(route):
            if route.request.resource_type in ["image", "font", "stylesheet", "media"]:
                await route.abort()
            else:
                await route.continue_()

        await self.page.route("**/*", route_request)

    async def _close_browser(self):
        if self.browser:
            await self.browser.close()

    async def scrape(self) -> List[Job]:
        """执行爬取"""
        await self._init_browser()

        self._api_responses = []

        async def handle_response(response):
            url = response.url
            if "/api/v1/search/job/posts" not in url:
                return
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type and "text/json" not in content_type:
                return
            try:
                data = await response.json()
                if data and data.get('code') == 0:
                    self._api_responses.append({
                        'list': data.get('data', {}).get('job_post_list', [])
                    })
            except Exception:
                pass

        self.page.on("response", handle_response)

        try:
            all_jobs = []

            # 社招
            self.progress("正在访问社招页面...")
            await self.page.goto(f"https://{self.domain}/experienced/position", timeout=self.PAGE_LOAD_TIMEOUT)
            await self.page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(0.5)

            social_jobs = await self._collect_jobs("社招")
            all_jobs.extend(social_jobs)

            self._api_responses = []

            # 校招
            self.progress("正在访问校招页面...")
            await self.page.goto(f"https://{self.domain}/campus/position", timeout=self.PAGE_LOAD_TIMEOUT)
            await self.page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(0.5)

            campus_jobs = await self._collect_jobs("校招")
            all_jobs.extend(campus_jobs)

            # 去重
            self.progress("正在处理数据...")
            seen = set()
            unique_jobs = []
            for job in all_jobs:
                key = f"{job.title}_{job.company}"
                if key not in seen:
                    seen.add(key)
                    unique_jobs.append(job)

            self.done(len(unique_jobs))
            return unique_jobs

        finally:
            await self._close_browser()

    async def _collect_jobs(self, job_type: str) -> List[Job]:
        """收集职位"""
        await asyncio.sleep(0.3)

        # 获取总页数
        total_pages = await self._get_page_count()
        max_pages = min(total_pages, self.max_pages) if self.max_pages else total_pages

        self.progress(f"检测到 {total_pages} 页，计划爬取 {max_pages} 页")

        # 翻页
        for page_num in range(2, max_pages + 1):
            self.progress_with_eta(page_num, max_pages, f"已获 {len(self._api_responses) * 10} 职位")
            clicked = await self._goto_page(page_num)
            if not clicked:
                break
            await asyncio.sleep(self.CLICK_DELAY)

        # 解析
        all_posts = []
        for resp in self._api_responses:
            all_posts.extend(resp.get('list', []))

        # 去重
        seen_ids = set()
        unique_posts = []
        for post in all_posts:
            post_id = post.get('id', '')
            if post_id not in seen_ids:
                seen_ids.add(post_id)
                unique_posts.append(post)

        return self._parse_job_posts(unique_posts, job_type)

    async def _get_page_count(self) -> int:
        return await self.page.evaluate("""() => {
            const items = document.querySelectorAll('.atsx-pagination-item');
            let maxPage = 1;
            for (let item of items) {
                const text = item.innerText.trim();
                if (/^\\d+$/.test(text)) {
                    const pageNum = parseInt(text);
                    if (pageNum > maxPage) maxPage = pageNum;
                }
            }
            return maxPage;
        }""")

    async def _goto_page(self, page_num: int) -> bool:
        return await self.page.evaluate("""(pageNum) => {
            const item = document.querySelector('.atsx-pagination-item-' + pageNum);
            if (item) { item.click(); return true; }
            const buttons = Array.from(document.querySelectorAll('button, [role="button"], a'));
            for (let btn of buttons) {
                const text = (btn.innerText || '').trim();
                if (text === '下一页' || text === '>') {
                    if (!btn.disabled) { btn.click(); return true; }
                }
            }
            return false;
        }""", page_num)

    def _parse_job_posts(self, job_post_list: List[Dict], job_type: str) -> List[Job]:
        jobs = []
        for post in job_post_list:
            title = post.get('title', '')
            description = post.get('description', '')
            requirement = post.get('requirement', '')

            # 薪资
            job_post_info = post.get('job_post_info', {}) or {}
            min_sal = job_post_info.get('min_salary', 0)
            max_sal = job_post_info.get('max_salary', 0)
            salary = f"{min_sal}-{max_sal}KCNY/月" if min_sal and max_sal else ""

            # 地点
            city_list = post.get('city_list', [])
            location = city_list[0].get('name', '') if city_list else ''

            # 发布时间
            publish_time = post.get('publish_time', 0)
            published_date = ''
            if publish_time:
                try:
                    published_date = datetime.fromtimestamp(publish_time / 1000).strftime('%Y-%m-%d')
                except:
                    pass

            job_id = post.get('id', '')
            url = self.get_job_url(job_id, job_type)

            full_desc = ""
            if description:
                full_desc += f"【职位描述】\n{description}"
            if requirement:
                if full_desc:
                    full_desc += "\n\n"
                full_desc += f"【职位要求】\n{requirement}"

            jobs.append(Job(
                title=title,
                company=self.company_name,
                salary=salary,
                location=location,
                job_type=job_type,
                description=full_desc,
                url=url,
                published_date=published_date
            ))

        return jobs

    def get_job_url(self, job_id: str = "", job_type: str = "") -> str:
        if not job_id:
            return f"https://{self.domain}/position/"
        prefix = "campus" if job_type == "校招" else "experienced"
        return f"https://{self.domain}/{prefix}/position/detail/{job_id}"