"""字节跳动招聘爬虫"""
import asyncio
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright, Browser, Page
from datetime import datetime

from .base import BaseScraper, Job


class ByteDanceScraper(BaseScraper):
    """字节跳动招聘系统爬虫 - 支持校招和社招"""

    def __init__(self, company_name: str, domain: str):
        super().__init__(company_name, domain)
        self.browser: Browser = None
        self.page: Page = None
        self._api_responses: List[Dict] = []
        self._current_signature: str = ""

    async def _init_browser(self):
        """初始化浏览器"""
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
        """执行爬取 - 拦截 API 响应获取数据"""
        await self._init_browser()

        # 设置 API 响应拦截器
        self._api_responses = []
        self._current_signature = ""

        async def handle_response(response):
            url = response.url

            # 捕获 signature
            if "_signature=" in url:
                sig_part = url.split("_signature=")[-1]
                self._current_signature = sig_part.split("&")[0] if "&" in sig_part else sig_part

            # 只拦截职位 API 请求
            if "/api/v1/search/job/posts" not in url:
                return

            # 只处理 JSON 响应
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type and "text/json" not in content_type:
                return

            try:
                data = await response.json()
                if data and data.get('code') == 0:
                    self._api_responses.append({
                        'list': data.get('data', {}).get('job_post_list', []),
                        'signature': self._current_signature
                    })
            except Exception:
                # 静默忽略解析错误
                pass

        self.page.on("response", handle_response)

        try:
            all_jobs = []

            # 爬取社招数据
            experienced_url = f"https://{self.domain}/experienced/position"
            await self.page.goto(experienced_url, timeout=60000)
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)

            # 获取社招数据
            jobs = await self._collect_jobs_with_pagination()
            all_jobs.extend(jobs)

            # 爬取校招数据
            campus_url = f"https://{self.domain}/campus/position"
            await self.page.goto(campus_url, timeout=60000)
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)

            # 获取校招数据
            campus_jobs = await self._collect_jobs_with_pagination()
            all_jobs.extend(campus_jobs)

            # 去重（按职位 ID）
            seen_ids = set()
            unique_jobs = []
            for job in all_jobs:
                # 使用标题 + 公司作为去重依据（API ID 可能在校招/社招中重复）
                job_key = f"{job.title}_{job.company}"
                if job_key not in seen_ids:
                    seen_ids.add(job_key)
                    unique_jobs.append(job)

            return unique_jobs

        finally:
            await self._close_browser()

    async def _collect_jobs_with_pagination(self) -> List[Job]:
        """收集当前页面的所有职位（包括翻页）"""
        initial_count = len(self._api_responses)

        # 等待初始数据加载
        await asyncio.sleep(2)

        # 尝试翻页
        for page_num in range(2, 11):  # 最多翻 10 页
            clicked = await self._goto_next_page()
            if not clicked:
                break

            await asyncio.sleep(2)

            # 检查是否有新数据
            if len(self._api_responses) <= initial_count:
                break

        # 收集所有职位数据
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

        return self._parse_job_posts(unique_posts)

    async def _goto_next_page(self) -> bool:
        """点击下一页"""
        return await self.page.evaluate("""() => {
            // 查找下一页按钮
            const buttons = Array.from(document.querySelectorAll('button, [role="button"], a'))
            for (let btn of buttons) {
                const text = (btn.innerText || btn.textContent || btn.getAttribute('aria-label') || '').trim()
                if (text === '下一页' || text === '›' || text === '>' || text === 'Next') {
                    // 检查是否禁用
                    if (btn.hasAttribute('disabled') || btn.getAttribute('aria-disabled') === 'true') {
                        return false
                    }
                    btn.click()
                    return true
                }
            }
            // 尝试点击页码
            for (let btn of buttons) {
                const text = (btn.innerText || btn.textContent || '').trim()
                if (/^\d+$/.test(text) && text !== '1') {
                    btn.click()
                    return true
                }
            }
            return false
        }""")

    def _parse_job_posts(self, job_post_list: List[Dict]) -> List[Job]:
        """解析 API 返回的职位数据"""
        jobs = []

        for post in job_post_list:
            # 基本信息
            title = post.get('title', '')
            description = post.get('description', '')
            requirement = post.get('requirement', '')

            # 职位代码
            code = post.get('code', '')

            # 薪资（字节跳动 API 中通常不显示）
            job_post_info = post.get('job_post_info', {}) or {}
            min_salary = job_post_info.get('min_salary', 0)
            max_salary = job_post_info.get('max_salary', 0)

            if min_salary and max_salary:
                salary = f"{min_salary}-{max_salary}KCNY/月"
            else:
                salary = ""

            # 地点
            city_list = post.get('city_list', [])
            if city_list and len(city_list) > 0:
                location = city_list[0].get('name', '')
            else:
                location = ''

            # 职位类型
            recruit_type = post.get('recruit_type', {}) or {}
            job_type = recruit_type.get('name', '')

            # 如果当前类型是"正式"，检查 parent
            if job_type == '正式':
                parent = recruit_type.get('parent', {})
                if parent:
                    parent_name = parent.get('name', '')
                    if parent_name in ['社招', '校招', '实习']:
                        job_type = parent_name

            # 如果还是没有获取到，根据 portal_type 判断
            if not job_type:
                job_type = '社招'  # 默认

            # 发布时间
            publish_time = post.get('publish_time', 0)
            if publish_time:
                try:
                    published_date = datetime.fromtimestamp(publish_time / 1000).strftime('%Y-%m-%d')
                except:
                    published_date = ''
            else:
                published_date = ''

            # 职位 ID 和链接
            job_id = post.get('id', '')
            url = self.get_job_url(job_id)

            # 合并描述和要求
            full_description = ""
            if description:
                full_description += f"【职位描述】\n{description}"
            if requirement:
                if full_description:
                    full_description += "\n\n"
                full_description += f"【职位要求】\n{requirement}"

            job = Job(
                title=title,
                company=self.company_name,
                salary=salary,
                location=location,
                job_type=job_type,
                description=full_description,
                url=url,
                published_date=published_date
            )
            jobs.append(job)

        return jobs

    def get_job_url(self, job_id: str = "") -> str:
        """获取职位投递链接"""
        if job_id:
            return f"https://{self.domain}/position/detail/{job_id}"
        return f"https://{self.domain}/position/"
