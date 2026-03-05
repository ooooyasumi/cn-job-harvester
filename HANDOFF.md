# JobHarvester 项目交接文档

## 项目概述

**项目名称**: JobHarvester - 招聘数据爬取工具

**项目位置**: `/Users/ooooyasumi/develop/Project/01_active/cn-job-harvester`

**当前版本**: v0.5.1

**功能描述**: 一个命令行工具，用于自动爬取公司招聘职位信息，支持多平台、多网站爬取，采用模块化架构，易于扩展。

---

## 已完成功能

### ✅ 核心功能

| 功能 | 状态 | 说明 |
|-----|------|------|
| 飞书招聘爬取 | ✅ | 使用 API 拦截方式获取数据 |
| 字节跳动爬虫 | ✅ | 支持校招/社招分开配置 |
| 腾讯招聘爬虫 | ✅ | 支持 join.qq.com(校招) 和 careers.tencent.com(社招) |
| 自动翻页 | ✅ | 自动检测页数并逐页获取 |
| CSV/Excel 导出 | ✅ | 使用 pandas 支持两种格式 |
| 交互式菜单 | ✅ | questionary 实现多选菜单 |
| 配置文件管理 | ✅ | YAML 格式公司配置 |
| 进度显示 | ✅ | 实时显示页数、百分比、ETA |
| Ctrl+C 中断保存 | ✅ | 中断时自动保存已爬取数据 |
| 模块化架构 | ✅ | 注册器模式，添加新爬虫只需创建文件 |

### ✅ 爬取字段

- 职位名称 (title)
- 公司名称 (company)
- 薪资范围 (salary)
- 工作地点 (location)
- 职位类型 (job_type) - 社招/校招
- 职位描述 (description)
- 投递链接 (url)
- 发布日期 (published_date)

---

## 项目结构

```
job-harvester/
├── config/
│   └── companies.yaml          # 公司配置文件（网站配置）
├── scrapers/
│   ├── __init__.py             # 模块入口，自动加载爬虫
│   ├── base.py                 # 基础爬虫类 + 统一进度显示
│   ├── registry.py             # 爬虫注册器
│   ├── feishu.py               # 飞书招聘爬虫
│   ├── bytedance.py            # 字节跳动爬虫
│   └── tencent.py              # 腾讯招聘爬虫
├── storage/
│   ├── __init__.py
│   └── csv_excel.py            # CSV/Excel 存储
├── cli.py                      # 命令行接口
├── main.py                     # 程序入口
├── _version.py                 # 版本号定义
├── CHANGELOG.md                # 更新日志
├── HANDOFF.md                  # 本文档
├── requirements.txt
└── README.md
```

---

## 核心代码说明

### 1. 模块化架构

#### 注册器模式 (`scrapers/registry.py`)

```python
# 注册爬虫
@ScraperRegistry.register('newcompany')
class NewCompanyScraper(BaseScraper):
    ...

# 获取爬虫
scraper_class = ScraperRegistry.get('bytedance')

# 列出所有爬虫
ScraperRegistry.list()  # ['feishu', 'bytedance', 'tencent']
```

#### 基类进度方法 (`scrapers/base.py`)

```python
class BaseScraper:
    def progress(self, message: str):
        """报告状态"""
        pass

    def progress_with_eta(self, current: int, total: int, extra_info: str = ""):
        """报告进度（带ETA）"""
        pass

    def done(self, count: int):
        """报告完成"""
        pass
```

### 2. 配置结构 (`config/companies.yaml`)

结构：**公司 → 网站 → 类型**

```yaml
companies:
  - name: 字节跳动
    sites:
      - name: 字节跳动社招
        scraper: bytedance
        domain: jobs.bytedance.com
        job_type: social        # 单一类型
        enabled: true
      - name: 字节跳动校招
        scraper: bytedance
        domain: jobs.bytedance.com
        job_type: campus
        enabled: true

  - name: 影视飓风
    sites:
      - name: 影视飓风
        scraper: feishu
        domain: mediastorm.jobs.feishu.cn
        job_types: [social, campus]  # 多种类型
        enabled: true
```

### 3. 交互式选择流程

1. **第一步**：选择招聘类型（校招/社招）- 空格多选
2. **第二步**：选择公司-网站 - 空格多选

---

## 添加新爬虫

### 步骤

1. **创建爬虫文件** `scrapers/newcompany.py`:

```python
from .base import BaseScraper, Job
from .registry import ScraperRegistry

@ScraperRegistry.register('newcompany')
class NewCompanyScraper(BaseScraper):
    """新公司招聘爬虫"""

    @classmethod
    def get_scraper_type(cls) -> str:
        return 'newcompany'

    async def scrape(self) -> List[Job]:
        # 使用 self.progress() 报告进度
        self.progress("正在启动浏览器...")
        self.progress_with_eta(5, 100, "已获 50 职位")

        # 实现爬取逻辑
        jobs = []
        # ...

        self.done(len(jobs))
        return jobs
```

2. **在 `scrapers/__init__.py` 添加导入**:

```python
from . import newcompany
```

3. **在 `config/companies.yaml` 添加配置**:

```yaml
companies:
  - name: 新公司
    sites:
      - name: 新公司
        scraper: newcompany
        domain: jobs.newcompany.com
        job_type: social
        enabled: true
```

---

## 使用方法

### 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 命令行使用

```bash
# 交互式选择（推荐）
python main.py

# 一键爬取所有
python main.py quick

# 按类型筛选
python main.py quick -t campus    # 仅校招
python main.py quick -t social    # 仅社招

# 交互式爬取
python main.py crawl

# 查看配置
python main.py config

# 查看已注册爬虫
python main.py scrapers

# 查看数据
python main.py list
```

---

## 版本发布流程

### 小版本更新（如 v0.5.1, v0.5.2）

1. 修改 `_version.py` 版本号
2. 更新 `CHANGELOG.md` 添加更新记录
3. 等待用户说"推送"后执行：

```bash
git add _version.py CHANGELOG.md
git commit -m "chore: 版本号更新到 v0.5.x"
git tag v0.5.x
```

### 大版本更新（如 v0.6.0, v1.0.0）

同上流程，版本号跨大版本。

### 推送到远程

```bash
git push && git push --tags
```

---

## 已完成版本

| 版本 | 日期 | 主要内容 |
|------|------|----------|
| v0.1.0 | - | 初始版本 |
| v0.2.0 | - | 飞书招聘支持 |
| v0.3.x | 2026-03-02 | 字节跳动/腾讯爬虫、进度显示、性能优化 |
| v0.4.0 | 2026-03-02 | 字节跳动爬虫 8 倍提速 |
| v0.5.0 | 2026-03-05 | 模块化架构重构：注册器模式、统一进度显示 |
| v0.5.1 | 2026-03-05 | 配置结构优化：网站配置替代渠道，支持多类型 |

---

## 待办事项

### v0.6.0（短期）

- [ ] 增量更新功能（基于职位 ID 去重）
- [ ] 错误处理和重试机制
- [ ] 更多招聘系统支持（北森、Moka）

### v1.0.0（长期）

- [ ] 完整的单元测试
- [ ] PyPI 发布
- [ ] Docker 镜像
- [ ] CI/CD 配置

---

## 已知问题

### 1. 大规模爬取时间较长

**现象**: 爬取字节跳动全部职位需要约 11 分钟

**状态**: ✅ 已优化（从 90 分钟优化到 11 分钟）

### 2. 薪资字段缺失

**现象**: 腾讯和字节跳动的职位薪资可能为空

**原因**: 平台 API 不返回薪资信息

**状态**: ✅ 正常行为

---

## 依赖版本

```
playwright>=1.40.0
typer>=0.9.0
pyyaml>=6.0
pandas>=2.0.0
openpyxl>=3.1.0
questionary>=2.0.0
```

---

## 合规声明

> **免责声明**: 本工具仅用于学习和研究目的，请遵守目标网站的 robots.txt 协议和使用条款，不要进行高频爬取，避免对目标服务器造成负担。

---

**交接日期**: 2026-03-05