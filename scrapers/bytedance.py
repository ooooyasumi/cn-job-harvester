"""字节跳动招聘爬虫 - 性能优化版"""
import asyncio
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright, Browser, Page
from datetime import datetime
import time
import signal

from .base import BaseScraper, Job


class ByteDanceScraper(BaseScraper):
    """字节跳动招聘系统爬虫 - 支持校招和社招"""

    # 优化配置
    PAGE_LOAD_TIMEOUT = 30000  # 页面加载超时 (毫秒)
    PAGE_WAIT_TIME = 0.5       # 页面加载后等待时间 (秒)
    CLICK_DELAY = 0.3          # 点击翻页间隔 (秒) - 激进模式
    BATCH_SIZE = 500           # 每批次页数
    BATCH_DELAY = 0.5          # 批次间休息 (秒)
    API_CONCURRENT = 20        # API 并发请求数

    def __init__(self, company_name: str, domain: str, status_callback=None, max_pages: int = None):
        super().__init__(company_name, domain)
        self.browser: Browser = None
        self.page: Page = None
        self._api_responses: List[Dict] = []
        self._current_signature: str = ""
        self._status_callback = status_callback
        self._max_pages = max_pages  # None 表示爬取全部

        # 进度追踪
        self._current_page = 0
        self._total_pages = 0
        self._start_time = 0
        self._jobs_collected: List[Job] = []  # 已爬取的职位数据（用于中断保存）

    async def _init_browser(self):
        """初始化浏览器 - 禁用资源加载以提升速度"""
        if self._status_callback:
            self._status_callback("正在启动浏览器...")
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)

        # 创建新页面
        self.page = await self.browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # 拦截不必要的请求
        async def route_request(route):
            # 跳过图片、字体、CSS 等资源
            if route.request.resource_type in ["image", "font", "stylesheet", "media"]:
                await route.abort()
            else:
                await route.continue_()

        await self.page.route("**/*", route_request)

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
            if self._status_callback:
                self._status_callback("正在访问社招页面...")
            experienced_url = f"https://{self.domain}/experienced/position"
            await self.page.goto(experienced_url, timeout=self.PAGE_LOAD_TIMEOUT)
            await self.page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(self.PAGE_WAIT_TIME)

            # 获取社招数据
            if self._status_callback:
                self._status_callback("正在获取社招职位数据...")
            jobs = await self._collect_jobs_with_pagination("社招", self._max_pages)
            all_jobs.extend(jobs)

            # 清空 API 响应列表，准备爬取校招
            self._api_responses = []

            # 爬取校招数据
            if self._status_callback:
                self._status_callback("正在访问校招页面...")
            campus_url = f"https://{self.domain}/campus/position"
            await self.page.goto(campus_url, timeout=self.PAGE_LOAD_TIMEOUT)
            await self.page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(self.PAGE_WAIT_TIME)

            # 获取校招数据
            if self._status_callback:
                self._status_callback("正在获取校招职位数据...")
            campus_jobs = await self._collect_jobs_with_pagination("校招", self._max_pages)
            all_jobs.extend(campus_jobs)

            # 去重（按职位 ID）
            if self._status_callback:
                self._status_callback("正在处理职位数据...")
            seen_ids = set()
            unique_jobs = []
            for job in all_jobs:
                # 使用标题 + 公司作为去重依据（API ID 可能在校招/社招中重复）
                job_key = f"{job.title}_{job.company}"
                if job_key not in seen_ids:
                    seen_ids.add(job_key)
                    unique_jobs.append(job)

            if self._status_callback:
                self._status_callback(f"爬取完成，共 {len(unique_jobs)} 个职位")
            return unique_jobs

        finally:
            await self._close_browser()

    async def _collect_jobs_with_pagination(self, job_type: str = "", max_pages_override: int = None) -> List[Job]:
        """收集当前页面的所有职位（包括翻页）- 使用优化的 API 直连方式

        Args:
            job_type: 职位类型（社招/校招）
            max_pages_override: 覆盖最大页数限制，None 表示爬取全部
        """
        # 等待初始数据加载
        await asyncio.sleep(0.3)

        # 获取总页数
        total_pages = await self._get_page_count()
        if self._status_callback:
            self._status_callback(f"检测到 {total_pages} 页数据")

        # 确定最大页数
        if max_pages_override is not None:
            max_pages = min(total_pages, max_pages_override)
        else:
            max_pages = total_pages  # 爬取全部

        if self._status_callback:
            self._status_callback(f"计划爬取 {max_pages} 页（约 {max_pages * 10} 个职位）...")

        # 使用 API 直连方式爬取
        return await self._collect_jobs_via_api(job_type, max_pages)

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

        if self._status_callback:
            self._status_callback(f"解析 {len(unique_posts)} 个职位数据...")
        return self._parse_job_posts(unique_posts, job_type)

    async def _get_page_count(self) -> int:
        """获取总页数"""
        return await self.page.evaluate("""() => {
            // 查找最后一个页码
            const items = document.querySelectorAll('.atsx-pagination-item');
            let maxPage = 1;
            for (let item of items) {
                const text = item.innerText.trim();
                if (/^\d+$/.test(text)) {
                    const pageNum = parseInt(text);
                    if (pageNum > maxPage) {
                        maxPage = pageNum;
                    }
                }
            }
            return maxPage;
        }""")

    async def _goto_page(self, page_num: int) -> bool:
        """翻到指定页"""
        return await self.page.evaluate("""(pageNum) => {
            // 查找对应的页码项
            const item = document.querySelector('.atsx-pagination-item-' + pageNum);
            if (item) {
                item.click();
                return true;
            }

            // 如果找不到直接页码，尝试点击"下一页"
            if (pageNum > 1) {
                const buttons = Array.from(document.querySelectorAll('button, [role="button"], a'));
                for (let btn of buttons) {
                    const text = (btn.innerText || btn.textContent || '').trim();
                    if (text === '下一页' || text === '>' || text === '›') {
                        if (!btn.disabled && btn.getAttribute('aria-disabled') !== 'true') {
                            btn.click();
                            return true;
                        }
                    }
                }
            }
            return false;
        }""", page_num)

    async def _goto_next_page(self) -> bool:
        """点击下一页（兼容方法）"""
        return await self.page.evaluate("""() => {
            // 查找所有页码项
            const items = document.querySelectorAll('.atsx-pagination-item');
            let currentPage = 1;
            let nextItem = null;

            for (let item of items) {
                const text = item.innerText.trim();
                if (/^\d+$/.test(text)) {
                    const isActive = item.classList.contains('atsx-pagination-item-active');
                    if (isActive) {
                        currentPage = parseInt(text);
                    } else if (parseInt(text) === currentPage + 1) {
                        nextItem = item;
                    }
                }
            }

            if (nextItem) {
                nextItem.click();
                return true;
            }

            // 尝试"下一页"按钮
            const buttons = Array.from(document.querySelectorAll('button, [role="button"], a'));
            for (let btn of buttons) {
                const text = (btn.innerText || btn.textContent || '').trim();
                if (text === '下一页' || text === '>' || text === '›') {
                    if (!btn.disabled && btn.getAttribute('aria-disabled') !== 'true') {
                        btn.click();
                        return true;
                    }
                }
            }
            return false;
        }""")

    def _parse_job_posts(self, job_post_list: List[Dict], job_type: str = "") -> List[Job]:
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

            # 职位类型：优先使用传入的类型参数
            if job_type:
                final_job_type = job_type
            else:
                # 如果没有传入类型，从 API 数据中获取
                recruit_type = post.get('recruit_type', {}) or {}
                final_job_type = recruit_type.get('name', '')

                # 如果当前类型是"正式"，检查 parent
                if final_job_type == '正式':
                    parent = recruit_type.get('parent', {})
                    if parent:
                        parent_name = parent.get('name', '')
                        if parent_name in ['社招', '校招', '实习']:
                            final_job_type = parent_name

                # 如果还是没有获取到，根据 portal_type 判断
                if not final_job_type:
                    final_job_type = '社招'  # 默认

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
            url = self.get_job_url(job_id, job_type)

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
                job_type=final_job_type,
                description=full_description,
                url=url,
                published_date=published_date
            )
            jobs.append(job)

        return jobs

    def get_job_url(self, job_id: str = "", job_type: str = "") -> str:
        """获取职位投递链接"""
        if not job_id:
            return f"https://{self.domain}/position/"

        # 根据职位类型确定路径前缀
        if job_type == "校招" or "实习" in job_type:
            prefix = "campus"
        else:
            prefix = "experienced"

        return f"https://{self.domain}/{prefix}/position/detail/{job_id}"

    async def _collect_jobs_via_api(self, job_type: str, max_pages: int) -> List[Job]:
        """通过点击翻页方式爬取职位数据（优化版）

        Args:
            job_type: 职位类型（社招/校招）
            max_pages: 最大爬取页数
        """
        # 初始化进度追踪
        self._total_pages = max_pages
        self._current_page = 1
        self._start_time = time.time()

        if self._status_callback:
            self._status_callback(f"使用优化模式爬取 {max_pages} 页数据...")

        # 批量翻页
        current_page = 1

        while current_page < max_pages:
            batch_end = min(current_page + self.BATCH_SIZE, max_pages)
            if self._status_callback:
                self._status_callback(f"正在爬取第 {current_page + 1}-{batch_end} 页...")

            for page_num in range(current_page + 1, batch_end + 1):
                # 计算进度信息
                progress_percent = (page_num / max_pages) * 100
                elapsed_time = time.time() - self._start_time
                avg_time_per_page = elapsed_time / (page_num - 1) if page_num > 1 else 0.5
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
                    self._status_callback(f"进度：{page_num}/{max_pages} ({progress_percent:.1f}%) | 已获 {len(self._api_responses) * 10} 职位 | 预计剩余：{eta_str}")

                clicked = await self._goto_page(page_num)
                if not clicked:
                    if self._status_callback:
                        self._status_callback("无法翻到下一页")
                    break

                self._current_page = page_num
                await asyncio.sleep(self.CLICK_DELAY)

            current_page = batch_end

            # 批次间休息
            if current_page < max_pages:
                if self._status_callback:
                    self._status_callback(f"已完成 {current_page}/{max_pages} 页，休息 {self.BATCH_DELAY} 秒...")
                await asyncio.sleep(self.BATCH_DELAY)

        if self._status_callback:
            self._status_callback(f"已获取 {len(self._api_responses)} 页数据")

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

        if self._status_callback:
            self._status_callback(f"解析 {len(unique_posts)} 个职位数据...")
        return self._parse_job_posts(unique_posts, job_type)
