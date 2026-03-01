# JobHarvester 项目交接文档

## 项目概述

**项目名称**: JobHarvester - 招聘数据爬取工具

**项目位置**: `/Users/ooooyasumi/develop/Project/01_active/project_cn-job-harvester`

**当前版本**: v0.2.0

**功能描述**: 一个命令行工具，用于自动爬取使用飞书招聘系统的公司职位信息，支持自动翻页、CSV/Excel 格式导出。

---

## 已完成功能

### ✅ 核心功能

| 功能 | 状态 | 说明 |
|-----|------|------|
| 飞书招聘爬取 | ✅ | 使用 API 拦截方式获取数据 |
| 自动翻页 | ✅ | 自动检测页数并逐页获取 |
| 完整字段 | ✅ | 包含职位描述和职位要求 |
| CSV/Excel 导出 | ✅ | 使用 pandas 支持两种格式 |
| 交互式菜单 | ✅ | questionary 实现多选菜单 |
| 配置文件管理 | ✅ | YAML 格式公司配置 |

### ✅ 爬取字段

- 职位名称 (title)
- 公司名称 (company)
- 薪资范围 (salary)
- 工作地点 (location)
- 职位类型 (job_type) - 社招/校招/实习
- 职位描述 (description) - 包含【职位描述】和【职位要求】
- 投递链接 (url)
- 发布日期 (published_date)

---

## 项目结构

```
job-harvester/
├── config/
│   └── companies.yaml          # 公司配置文件
├── scrapers/
│   ├── __init__.py
│   ├── base.py                 # 基础爬虫类 (Job dataclass, BaseScraper)
│   └── feishu.py               # 飞书招聘爬虫 (FeishuScraper)
├── storage/
│   ├── __init__.py
│   └── csv_excel.py            # CSV/Excel 存储 (JobStorage)
├── cli.py                      # 命令行接口 (Typer + questionary)
├── main.py                     # 程序入口
├── requirements.txt
└── README.md
```

---

## 核心代码说明

### 1. `scrapers/feishu.py` - 飞书招聘爬虫

**核心方法**:

- `scrape()` - 主爬取方法，拦截 API 响应获取数据
- `_get_page_count()` - 检测总页数
- `_goto_page(page_num)` - 翻到指定页
- `_parse_job_posts(job_post_list)` - 解析 API 返回的职位数据

**API 端点**:
```
https://{domain}/api/v1/search/job/posts?keyword=&limit=100&offset=0&...&_signature={signature}
```

**API 响应结构**:
```json
{
  "code": 0,
  "data": {
    "job_post_list": [
      {
        "id": "7605922195206097203",
        "title": "大数据开发工程师",
        "description": "...",
        "requirement": "...",
        "job_post_info": {"min_salary": 15, "max_salary": 30},
        "city_list": [{"name": "杭州"}],
        "recruit_type": {"name": "全职", "parent": {"name": "社招"}},
        "publish_time": 1770892089298
      }
    ]
  }
}
```

### 2. `scrapers/base.py` - 基础类

```python
@dataclass
class Job:
    title: str
    company: str
    salary: str
    location: str
    job_type: str
    description: str
    url: str
    published_date: str
```

### 3. `cli.py` - 命令行接口

**命令**:
- `python main.py` - 交互式模式（默认）
- `python main.py crawl -c "公司名"` - 爬取指定公司
- `python main.py crawl --all` - 爬取所有配置的公司
- `python main.py crawl -i` - 交互式选择公司
- `python main.py list jobs.csv` - 查看已保存数据
- `python main.py init` - 初始化配置文件

---

## 使用方法

### 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 快速开始

```bash
# 方式 1：交互式菜单（推荐）
python main.py

# 方式 2：爬取指定公司
python main.py crawl -c "影视飓风"

# 方式 3：爬取所有配置的公司
python main.py crawl --all

# 方式 4：导出数据
python main.py crawl -c "影视飓风" -f excel -o jobs.xlsx
```

---

## 当前配置

### `config/companies.yaml`

```yaml
companies:
  - name: 影视飓风
    domain: mediastorm.jobs.feishu.cn
    type: feishu
    enabled: true
```

---

## 已知问题

### 1. API Signature 获取问题

**现象**: 控制台显示 "警告：无法获取 signature，尝试不使用 signature 请求"

**原因**: 某些飞书招聘页面的 signature 获取逻辑不完善

**影响**: 不影响实际爬取功能，因为使用了 API 拦截方式

**待优化**: 可以更优雅地处理 signature 获取

### 2. API 响应解析失败

**现象**: 控制台显示 "解析 API 响应失败：Expecting value: line 1 column 1 (char 0)"

**原因**: 某些 API 请求返回的是 HTML 而非 JSON（如 logo、图片等）

**影响**: 不影响实际功能，因为目标 API 请求仍能正常解析

**待优化**: 可以添加更精确的 URL 过滤

### 3. 翻页后 API 数据收集

**当前实现**: 翻页后重新收集所有 API 响应，然后去重

**潜在问题**: 如果翻页逻辑变化，可能导致数据重复或丢失

**待优化**: 可以更精确地控制每页数据的获取

---

## 待办事项 (TODO)

### v0.3.0 计划

- [ ] **增量更新（去重）**
  - 基于职位 ID 或链接去重
  - 支持只获取新职位

- [ ] **错误处理和重试机制**
  - 网络错误重试
  - API 失败降级方案

- [ ] **更多招聘系统支持**
  - 北森招聘系统
  - Moka 招聘系统

### v1.0.0 计划

- [ ] 完整的单元测试
- [ ] 详细的使用文档
- [ ] 性能优化
- [ ] PyPI 发布

---

## 测试方法

### 功能测试

```bash
# 测试爬取单家公司
python main.py crawl -c "影视飓风" -o test.csv

# 验证数据
python main.py list test.csv

# 清理
rm test.csv
```

### 预期输出

```
解析 API 响应失败：Expecting value: line 1 column 1 (char 0)
  API 获取到 10 个职位
  检测到 3 页数据
  正在翻到第 2 页...
  正在翻到第 3 页...
  去重后共 29 个职位
爬取到 29 个职位
已保存到 test.csv
```

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

## 重要提示

1. **API 拦截方式**: 当前实现依赖 Playwright 拦截 API 响应，如果飞书招聘改变 API 结构，需要更新 `_parse_job_posts` 方法

2. **翻页逻辑**: 当前翻页通过点击页码按钮实现，如果 UI 变化需要更新 `_goto_page` 方法

3. **签名参数**: API 需要 `_signature` 参数，当前实现通过页面元素获取，如果失效需要重新分析

4. **数据去重**: 当前使用职位 ID 去重，确保 `post.get('id')` 字段有效

---

## 联系方式

如有问题，请查看项目 README.md 或源代码注释。

**交接日期**: 2026-03-02
