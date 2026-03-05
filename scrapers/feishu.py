"""飞书招聘爬虫"""
import asyncio
from typing import List, Dict
from playwright.async_api import async_playwright, Browser, Page
from datetime import datetime

from .base import BaseScraper, Job
from .registry import ScraperRegistry


@ScraperRegistry.register('feishu')
class FeishuScraper(BaseScraper):
    """飞书招聘系统爬虫"""

    @classmethod
    def get_scraper_type(cls) -> str:
        return 'feishu'

    def __init__(self, company_name: str, domain: str, **kwargs):
        super().__init__(company_name, domain, **kwargs)
        self.browser: Browser = None
        self.page: Page = None
        self._company_name_from_page: str = ""
        self._api_responses: List[Dict] = []

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
            if "/api/v1/search/job/posts" not in response.url:
                return
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type and "text/json" not in content_type:
                return
            try:
                data = await response.json()
                if data and data.get('code') == 0:
                    self._api_responses.append({
                        'list': data.get('data', {}).get('job_post_list', []),
                        'total': data.get('data', {}).get('total', 0)
                    })
            except Exception:
                pass

        self.page.on("response", handle_response)

        try:
            # 访问首页
            self.progress("正在访问招聘首页...")
            url = f"https://{self.domain}/index/"
            await self.page.goto(url, timeout=60000)
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)

            # 获取公司名称
            self._company_name_from_page = await self._get_company_name()

            # 收集初始数据
            all_posts = []
            for resp in self._api_responses:
                all_posts.extend(resp.get('list', []))

            if not all_posts:
                self.progress("API 获取失败，尝试页面提取...")
                self.jobs = await self._scrape_from_page()
            else:
                # 检测分页
                self.progress("检测分页...")
                page_count = await self._get_page_count()

                if page_count > 1:
                    # 翻页爬取
                    for page_num in range(2, page_count + 1):
                        self.progress_with_eta(page_num, page_count, f"已获 {len(all_posts)} 职位")
                        await self._goto_page(page_num)
                        await asyncio.sleep(2)
                        # 重新收集
                        all_posts = []
                        for resp in self._api_responses:
                            all_posts.extend(resp.get('list', []))

                # 去重
                self.progress("正在处理数据...")
                seen_ids = set()
                unique_posts = []
                for post in all_posts:
                    post_id = post.get('id', '')
                    if post_id not in seen_ids:
                        seen_ids.add(post_id)
                        unique_posts.append(post)

                self.jobs = self._parse_job_posts(unique_posts)

            self.done(len(self.jobs))
            return self.jobs

        finally:
            await self._close_browser()

    async def _get_company_name(self) -> str:
        """从页面获取公司名称"""
        name = await self.page.evaluate("""() => {
            const titleEl = document.querySelector('meta[name="description"]');
            if (titleEl) {
                const content = titleEl.getAttribute('content');
                const start = content.indexOf('到');
                const end = content.indexOf('，');
                if (start >= 0 && end > start) {
                    return content.substring(start + 1, end);
                }
            }
            return '';
        }""")
        return name or self.company_name

    async def _get_page_count(self) -> int:
        """获取总页数"""
        return await self.page.evaluate("""() => {
            const pager = document.querySelector('[class*="page"], [class*="Page"]');
            if (!pager) return 1;
            const buttons = pager.querySelectorAll('button, a, [role="button"]');
            let maxPage = 1;
            for (const btn of buttons) {
                const text = btn.innerText.trim() || btn.textContent.trim();
                if (/^\\d+$/.test(text)) {
                    const pageNum = parseInt(text);
                    if (pageNum > maxPage) maxPage = pageNum;
                }
            }
            return maxPage;
        }""")

    async def _goto_page(self, page_num: int):
        """翻到指定页"""
        await self.page.evaluate("""(pageNum) => {
            const pager = document.querySelector('[class*="page"], [class*="Page"]');
            if (!pager) return;
            const buttons = pager.querySelectorAll('button, a, [role="button"]');
            for (const btn of buttons) {
                const text = btn.innerText.trim() || btn.textContent.trim();
                if (text === String(pageNum)) {
                    btn.click();
                    return;
                }
            }
            if (pageNum > 1) {
                for (const btn of buttons) {
                    const text = btn.innerText.trim();
                    if (text === '>' || text === '下一页') {
                        btn.click();
                        return;
                    }
                }
            }
        }""", page_num)

    async def _scrape_from_page(self) -> List[Job]:
        """从页面提取（备用方案）"""
        raw_data = await self.page.evaluate(self._get_extract_script())
        return self._parse_page_data(raw_data)

    def _get_extract_script(self) -> str:
        return """() => {
            const result = { positions: [], companyName: '' };
            const titleEl = document.querySelector('meta[name="description"]');
            if (titleEl) {
                const content = titleEl.getAttribute('content');
                const start = content.indexOf('到');
                const end = content.indexOf('，');
                if (start >= 0 && end > start) {
                    result.companyName = content.substring(start + 1, end);
                }
            }
            const allDivs = document.querySelectorAll('div');
            for (let div of allDivs) {
                const text = div.innerText.trim();
                if (/\\d+-\\d+K/.test(text) && text.includes('CNY')) {
                    const lines = text.split('\\n').map(l => l.trim()).filter(l => l);
                    if (lines.length < 4) continue;
                    let positionName = '';
                    let salaryIndex = -1;
                    let infoLine = '';
                    for (let i = 0; i < lines.length; i++) {
                        if (/\\d+-\\d+K/.test(lines[i]) && lines[i].includes('CNY')) {
                            salaryIndex = i;
                            if (i > 0) positionName = lines[i - 1];
                            if (i + 1 < lines.length) infoLine = lines[i + 1];
                            break;
                        }
                    }
                    if (positionName && salaryIndex > 0) {
                        result.positions.push({
                            name: positionName,
                            salary: lines[salaryIndex],
                            infoLine: infoLine,
                            rawLines: lines
                        });
                    }
                }
            }
            const seen = new Set();
            result.positions = result.positions.filter(pos => {
                if (seen.has(pos.name)) return false;
                seen.add(pos.name);
                return true;
            });
            return result;
        }"""

    def _parse_job_posts(self, job_post_list: List[Dict]) -> List[Job]:
        """解析 API 返回的职位数据"""
        jobs = []
        company = self._company_name_from_page or self.company_name

        for post in job_post_list:
            title = post.get('title', '')
            description = post.get('description', '')
            requirement = post.get('requirement', '')

            # 薪资
            job_post_info = post.get('job_post_info', {}) or {}
            min_salary = job_post_info.get('min_salary', 0)
            max_salary = job_post_info.get('max_salary', 0)
            salary = f"{min_salary}-{max_salary}KCNY/月" if min_salary and max_salary else ""

            # 地点
            city_list = post.get('city_list', [])
            location = city_list[0].get('name', '') if city_list else ''

            # 职位类型
            recruit_type = post.get('recruit_type', {}) or {}
            job_type = recruit_type.get('name', '')
            if job_type == '全职':
                parent = recruit_type.get('parent', {})
                if parent:
                    parent_name = parent.get('name', '')
                    if parent_name in ['社招', '校招']:
                        job_type = parent_name
            if not job_type:
                job_type = '社招'

            # 发布时间
            publish_time = post.get('publish_time', 0)
            published_date = ''
            if publish_time:
                try:
                    published_date = datetime.fromtimestamp(publish_time / 1000).strftime('%Y-%m-%d')
                except:
                    pass

            job_id = post.get('id', '')
            url = self.get_job_url(job_id)

            full_description = ""
            if description:
                full_description += f"【职位描述】\n{description}"
            if requirement:
                if full_description:
                    full_description += "\n\n"
                full_description += f"【职位要求】\n{requirement}"

            jobs.append(Job(
                title=title,
                company=company,
                salary=salary,
                location=location,
                job_type=job_type,
                description=full_description,
                url=url,
                published_date=published_date
            ))

        return jobs

    def _parse_page_data(self, raw_data: Dict) -> List[Job]:
        """解析页面数据（备用方案）"""
        import re
        jobs = []
        company = raw_data.get('companyName', self.company_name)

        for pos in raw_data.get('positions', []):
            info_line = pos.get('infoLine', '')
            salary = pos.get('salary', '')

            location = ''
            location_pattern = r'(杭州|北京|上海|广州|深圳|武汉|成都|南京|苏州|西安|重庆|长沙|合肥|郑州|天津|青岛|宁波|东莞|佛山)'
            location_match = re.search(location_pattern, info_line)
            if location_match:
                location = location_match.group(1)

            job_type = '社招'
            if '校招' in info_line:
                job_type = '校招'

            jobs.append(Job(
                title=pos.get('name', ''),
                company=company,
                salary=salary,
                location=location,
                job_type=job_type,
                description='',
                url=self.get_job_url(),
                published_date=''
            ))

        return jobs

    def get_job_url(self, job_id: str = "") -> str:
        if job_id:
            return f"https://{self.domain}/job/{job_id}"
        return f"https://{self.domain}/index/"