"""飞书招聘爬虫 - 使用 API 方式"""
import asyncio
import re
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright, Browser, Page

from .base import BaseScraper, Job


class FeishuScraper(BaseScraper):
    """飞书招聘系统爬虫 - 使用 API 获取数据"""

    def __init__(self, company_name: str, domain: str):
        super().__init__(company_name, domain)
        self.browser: Browser = None
        self.page: Page = None
        self._company_name_from_page: str = ""
        self._api_responses: List[Dict] = []

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

    async def scrape(self) -> List[Job]:
        """执行爬取 - 拦截 API 响应获取数据"""
        await self._init_browser()

        # 设置 API 响应拦截器
        self._api_responses = []

        async def handle_response(response):
            # 只拦截 API 请求，过滤非 API 请求
            if "/api/v1/search/job/posts" not in response.url:
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
                        'total': data.get('data', {}).get('total', 0)
                    })
            except Exception:
                # 静默忽略解析错误（非目标 API 请求）
                pass

        self.page.on("response", handle_response)

        try:
            # 访问首页
            url = f"https://{self.domain}/index/"
            await self.page.goto(url, timeout=60000)
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)  # 等待 API 请求完成

            # 获取公司名称
            self._company_name_from_page = await self._get_company_name()

            # 检查是否获取到 API 数据
            all_posts = []
            for resp in self._api_responses:
                all_posts.extend(resp.get('list', []))

            if not all_posts:
                print("未能通过 API 获取数据，尝试从页面提取...")
                self.jobs = await self._scrape_from_page()
            else:
                print(f"  API 获取到 {len(all_posts)} 个职位")

                # 检查是否有翻页
                # 获取总页数
                page_count = await self._get_page_count()
                print(f"  检测到 {page_count} 页数据")

                # 如果有翻页，逐页获取
                if page_count > 1:
                    for page_num in range(2, page_count + 1):
                        print(f"  正在翻到第 {page_num} 页...")
                        await self._goto_page(page_num)
                        await asyncio.sleep(2)  # 等待数据加载

                # 重新收集所有数据
                all_posts = []
                for resp in self._api_responses:
                    all_posts.extend(resp.get('list', []))

                # 去重（按职位 ID）
                seen_ids = set()
                unique_posts = []
                for post in all_posts:
                    post_id = post.get('id', '')
                    if post_id not in seen_ids:
                        seen_ids.add(post_id)
                        unique_posts.append(post)

                print(f"  去重后共 {len(unique_posts)} 个职位")
                self.jobs = self._parse_job_posts(unique_posts)

            return self.jobs

        finally:
            await self._close_browser()

    async def _get_page_count(self) -> int:
        """获取总页数"""
        return await self.page.evaluate("""() => {
            const pager = document.querySelector('[class*="page"], [class*="Page"]');
            if (!pager) return 1;

            // 查找所有页码按钮
            const buttons = pager.querySelectorAll('button, a, [role="button"]');
            let maxPage = 1;
            for (const btn of buttons) {
                const text = btn.innerText.trim() || btn.textContent.trim();
                if (/^\d+$/.test(text)) {
                    const pageNum = parseInt(text);
                    if (pageNum > maxPage) {
                        maxPage = pageNum;
                    }
                }
            }
            return maxPage;
        }""")

    async def _goto_page(self, page_num: int):
        """翻到指定页"""
        await self.page.evaluate("""(pageNum) => {
            const pager = document.querySelector('[class*="page"], [class*="Page"]');
            if (!pager) return;

            // 查找页码按钮
            const buttons = pager.querySelectorAll('button, a, [role="button"]');
            for (const btn of buttons) {
                const text = btn.innerText.trim() || btn.textContent.trim();
                if (text === String(pageNum)) {
                    btn.click();
                    return;
                }
            }

            // 如果没有直接页码，尝试点击"下一页"
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
        """从页面提取职位数据（备用方案）"""
        raw_data = await self.page.evaluate(self._get_extract_script())
        return self._parse_page_data(raw_data)

    def _get_extract_script(self) -> str:
        """返回用于提取数据的 JavaScript 脚本"""
        return """() => {
            const result = {
                positions: [],
                companyName: ''
            };

            // 获取公司名称
            const titleEl = document.querySelector('meta[name="description"]');
            if (titleEl) {
                const content = titleEl.getAttribute('content');
                const start = content.indexOf('到');
                const end = content.indexOf('，');
                if (start >= 0 && end > start) {
                    result.companyName = content.substring(start + 1, end);
                }
            }

            // 查找所有包含薪资信息的职位卡片
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
                            if (i > 0) {
                                positionName = lines[i - 1];
                            }
                            if (i + 1 < lines.length) {
                                infoLine = lines[i + 1];
                            }
                            break;
                        }
                    }

                    if (positionName && salaryIndex > 0) {
                        result.positions.push({
                            name: positionName,
                            salary: lines[salaryIndex],
                            infoLine: infoLine,
                            rawLines: lines,
                            fullText: text
                        });
                    }
                }
            }

            // 去重
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
            # 基本信息
            title = post.get('title', '')
            description = post.get('description', '')
            requirement = post.get('requirement', '')

            # 薪资
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

            # 职位类型（社招/校招/实习）
            recruit_type = post.get('recruit_type', {}) or {}
            job_type = recruit_type.get('name', '')

            # 如果当前类型是"全职"，检查 parent 是否是"社招"或"校招"
            if job_type == '全职':
                parent = recruit_type.get('parent', {})
                if parent:
                    parent_name = parent.get('name', '')
                    if parent_name in ['社招', '校招', '实习']:
                        job_type = parent_name

            # 如果还是没有获取到，使用默认值
            if not job_type:
                job_type = '社招'  # 默认社招

            # 发布时间
            publish_time = post.get('publish_time', 0)
            if publish_time:
                from datetime import datetime
                try:
                    published_date = datetime.fromtimestamp(publish_time / 1000).strftime('%Y-%m-%d')
                except:
                    published_date = ''
            else:
                published_date = ''

            # 职位 ID 和链接
            job_id = post.get('id', '')
            url = self.get_job_url(job_id)

            # 合并描述和要求（分开保存）
            full_description = ""
            if description:
                full_description += f"【职位描述】\n{description}"
            if requirement:
                if full_description:
                    full_description += "\n\n"
                full_description += f"【职位要求】\n{requirement}"

            job = Job(
                title=title,
                company=company,
                salary=salary,
                location=location,
                job_type=job_type,
                description=full_description,
                url=url,
                published_date=published_date
            )
            jobs.append(job)

        return jobs

    def _parse_page_data(self, raw_data: Dict[str, Any]) -> List[Job]:
        """解析从页面提取的数据（备用方案）"""
        import re
        jobs = []
        company = raw_data.get('companyName', self.company_name)

        for pos in raw_data.get('positions', []):
            lines = pos.get('rawLines', [])
            info_line = pos.get('infoLine', '')

            salary = pos.get('salary', '')

            # 解析地点和类型
            location = ''
            job_type = ''

            location_pattern = r'(杭州 | 北京 | 上海 | 广州 | 深圳 | 武汉 | 成都 | 南京 | 苏州 | 西安 | 重庆 | 长沙 | 合肥 | 郑州 | 天津 | 青岛 | 宁波 | 东莞 | 佛山)'
            location_match = re.search(location_pattern, info_line)
            if location_match:
                location = location_match.group(1)

            if '社招' in info_line:
                job_type = '社招'
            elif '校招' in info_line:
                job_type = '校招'
            elif '实习' in info_line:
                job_type = '实习'
            else:
                job_type = '全职'

            # 职位描述
            description_lines = []
            skip_patterns = [
                r'^职位$', r'^官网主页$', r'^登录$', r'^搜索$',
                r'^筛选$', r'^清除$', r'^城市$', r'^职能分类$',
                r'^开启新的工作', r'^\d+-\d+K'
            ]

            in_description = False
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if any(re.match(p, line) for p in skip_patterns):
                    continue
                if salary.split('CNY')[0] in line:
                    continue
                if any(t in line for t in ['社招', '校招', '实习', '全职']):
                    continue
                if line == pos.get('name', ''):
                    in_description = True
                    continue
                if in_description and len(line) > 5:
                    description_lines.append(line)

            description = '\n'.join(description_lines[:10])

            job = Job(
                title=pos.get('name', ''),
                company=company,
                salary=salary,
                location=location,
                job_type=job_type,
                description=description,
                url=self.get_job_url(),
                published_date=''
            )
            jobs.append(job)

        return jobs

    def get_job_url(self, job_id: str = "") -> str:
        """获取职位投递链接"""
        if job_id:
            return f"https://{self.domain}/job/{job_id}"
        return f"https://{self.domain}/index/"
