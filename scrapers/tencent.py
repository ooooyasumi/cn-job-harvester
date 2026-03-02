"""腾讯招聘爬虫 - 支持校招/实习/社招"""
import asyncio
from typing import List, Dict, Any
from playwright.async_api import async_playwright, Browser, Page
from datetime import datetime
import time

from .base import BaseScraper, Job


class TencentScraper(BaseScraper):
    """腾讯招聘系统爬虫 - 支持 join.qq.com 和 careers.tencent.com"""

    def __init__(self, company_name: str, domain: str, status_callback=None, max_pages: int = None):
        super().__init__(company_name, domain)
        self.browser: Browser = None
        self.page: Page = None
        self._api_responses: List[Dict] = []
        self._status_callback = status_callback
        self._max_pages = max_pages

        # 进度追踪
        self._current_page = 0
        self._total_pages = 0
        self._start_time = 0

    async def _init_browser(self):
        """初始化浏览器"""
        if self._status_callback:
            self._status_callback("正在启动浏览器...")
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)
        self.page = await self.browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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

            # 拦截职位搜索 API
            if "searchPosition" in url or "/post/Query" in url:
                content_type = response.headers.get("content-type", "")
                if "application/json" not in content_type and "text/json" not in content_type:
                    return

                try:
                    data = await response.json()
                    self._api_responses.append({
                        'url': url,
                        'data': data,
                        'type': 'searchPosition' if 'searchPosition' in url else 'Query'
                    })
                except Exception:
                    pass

        self.page.on("response", handle_response)

        try:
            all_jobs = []

            # 爬取校招/实习数据 (join.qq.com)
            if self._status_callback:
                self._status_callback("正在访问校招页面...")

            await self.page.goto("https://join.qq.com/post.html", timeout=60000)
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)

            # 获取校招数据
            if self._status_callback:
                self._status_callback("正在获取校招/实习职位数据...")

            campus_jobs = await self._collect_join_qq_jobs()
            all_jobs.extend(campus_jobs)

            # 清空 API 响应列表，准备爬取社招
            self._api_responses = []

            # 爬取社招数据 (careers.tencent.com)
            if self._status_callback:
                self._status_callback("正在访问社招页面...")

            await self.page.goto("https://careers.tencent.com/search.html", timeout=60000)
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)

            # 获取社招数据
            if self._status_callback:
                self._status_callback("正在获取社招职位数据...")

            social_jobs = await self._collect_careers_tencent_jobs()
            all_jobs.extend(social_jobs)

            if self._status_callback:
                self._status_callback(f"爬取完成，共 {len(all_jobs)} 个职位")

            return all_jobs

        finally:
            await self._close_browser()

    async def _collect_join_qq_jobs(self) -> List[Job]:
        """收集 join.qq.com 的职位（校招/实习）"""
        jobs = []

        # 从 API 响应中提取职位
        for resp in self._api_responses:
            if resp['type'] != 'searchPosition':
                continue

            data = resp['data']
            if data.get('status') != 0:
                continue

            position_list = data.get('data', {}).get('positionList', [])

            for pos in position_list:
                # 提取职位信息
                job = Job(
                    title=pos.get('positionTitle', ''),
                    company=self.company_name,
                    salary='',  # 校招通常不显示薪资
                    location=self._parse_join_qq_cities(pos.get('workCities', '')),
                    job_type=pos.get('projectName', '校招'),
                    description=f"职位 ID: {pos.get('postId', '')}\n事业群：{pos.get('bgs', '')}",
                    url=f"https://join.qq.com/post_detail.html?pid={pos.get('postId', '')}",
                    published_date=datetime.now().strftime('%Y-%m-%d')
                )
                jobs.append(job)

        if self._status_callback:
            self._status_callback(f"获取到 {len(jobs)} 个校招/实习职位")

        return jobs

    def _parse_join_qq_cities(self, cities_str: str) -> str:
        """解析 join.qq.com 的城市字符串"""
        if not cities_str:
            return ''
        # "深圳总部 北京 上海 广州 成都 杭州 " -> "深圳"
        cities = cities_str.strip().split(' ')
        return cities[0] if cities else ''

    async def _collect_careers_tencent_jobs(self) -> List[Job]:
        """收集 careers.tencent.com 的职位（社招）"""
        # 获取总页数
        total_count = 0
        for resp in self._api_responses:
            if resp['type'] == 'Query':
                data = resp['data']
                if data.get('Code') == 200:
                    total_count = data.get('Data', {}).get('Count', 0)
                    break

        total_pages = (total_count + 9) // 10  # 每页 10 条
        # 默认爬取全部，如果指定了 max_pages 则使用限制
        max_pages = self._max_pages if self._max_pages else total_pages

        if self._status_callback:
            self._status_callback(f"检测到 {total_pages} 页数据（共{total_count}个职位），计划爬取 {max_pages} 页")

        # 初始化进度追踪
        self._total_pages = max_pages
        self._current_page = 1
        self._start_time = time.time()

        # 翻页爬取
        for page_num in range(2, max_pages + 1):
            # 计算进度信息
            progress_percent = (page_num / max_pages) * 100
            elapsed_time = time.time() - self._start_time
            avg_time_per_page = elapsed_time / (page_num - 1) if page_num > 1 else 2
            remaining_pages = max_pages - page_num
            eta_seconds = remaining_pages * avg_time_per_page

            # 格式化 ETA 时间
            if eta_seconds < 60:
                eta_str = f"{int(eta_seconds)}秒"
            elif eta_seconds < 3600:
                eta_str = f"{int(eta_seconds / 60)}分钟"
            else:
                eta_str = f"{int(eta_seconds / 3600)}小时{int((eta_seconds % 3600) / 60)}分钟"

            if self._status_callback:
                self._status_callback(f"进度：{page_num}/{max_pages} ({progress_percent:.1f}%) | 预计剩余：{eta_str}")

            await self._goto_page(page_num)
            self._current_page = page_num
            await asyncio.sleep(2)

        # 解析所有职位
        jobs = []
        seen_ids = set()

        for resp in self._api_responses:
            if resp['type'] != 'Query':
                continue

            data = resp['data']
            if data.get('Code') != 200:
                continue

            posts = data.get('Data', {}).get('Posts', [])

            for post in posts:
                post_id = post.get('PostId', '')
                if post_id in seen_ids:
                    continue
                seen_ids.add(post_id)

                job = Job(
                    title=post.get('RecruitPostName', ''),
                    company=self.company_name,
                    salary='',  # 社招通常不显示薪资
                    location=post.get('LocationName', ''),
                    job_type='社招',
                    description=post.get('Responsibility', ''),
                    url=post.get('PostURL', ''),
                    published_date=self._parse_tencent_date(post.get('LastUpdateTime', ''))
                )
                jobs.append(job)

        if self._status_callback:
            self._status_callback(f"获取到 {len(jobs)} 个社招职位")

        return jobs

    def _parse_tencent_date(self, date_str: str) -> str:
        """解析腾讯日期格式"""
        if not date_str:
            return ''
        # "2026 年 03 月 02 日" -> "2026-03-02"
        return date_str.replace('年', '-').replace('月', '-').replace('日', '')

    async def _goto_page(self, page_num: int):
        """翻到指定页"""
        # 通过 JavaScript 模拟点击分页
        result = await self.page.evaluate("""(pageNum) => {
            // 查找所有页码元素
            const pageItems = document.querySelectorAll('[class*="page"]');
            for (let item of pageItems) {
                const text = item.innerText.trim();
                if (text === String(pageNum)) {
                    item.click();
                    return true;
                }
            }
            // 查找下一页按钮
            const buttons = Array.from(document.querySelectorAll('button, a, [role="button"]'));
            for (let btn of buttons) {
                const text = btn.innerText.trim();
                if (text === '下一页' || text === '>' || text === '»') {
                    if (!btn.disabled && btn.getAttribute('aria-disabled') !== 'true') {
                        btn.click();
                        return true;
                    }
                }
            }
            return false;
        }""", page_num)

        return result
