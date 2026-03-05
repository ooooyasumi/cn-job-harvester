# JobHarvester - 招聘数据爬取工具

一个命令行工具，用于自动爬取公司招聘职位信息，支持 CSV/Excel 格式导出。采用可扩展的模块化架构，支持多种招聘平台。

## 功能特性

- **两大招聘类型**：校招、社招
- **多渠道支持**：每个公司可有多个招聘渠道（如淘天集团、千问团队等）
- **交互式选择**：先选类型 → 再选渠道，支持多选
- **模块化架构**：添加新爬虫只需创建一个文件
- **多种导出格式**：支持 CSV、Excel 格式

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 基本使用

```bash
# 方式 1：交互式选择（推荐）
python main.py

# 方式 2：一键爬取所有
python main.py quick

# 方式 3：指定类型爬取
python main.py quick -t campus           # 仅校招
python main.py quick -t social           # 仅社招
python main.py quick -t campus,social    # 校招+社招
```

### 交互式选择流程

运行 `python main.py` 后：

1. **第一步：选择招聘类型**
   - 使用 `↑` `↓` 键移动
   - `空格键` 选择/取消
   - `回车键` 确认
   - 可多选校招、社招

2. **第二步：选择公司和网站**
   - 显示符合选中类型的所有网站
   - 同样支持多选

## 配置结构

编辑 `config/companies.yaml` 添加公司：

```yaml
companies:
  - name: 字节跳动
    sites:
      - name: 字节跳动社招
        scraper: bytedance
        domain: jobs.bytedance.com
        job_type: social
        enabled: true
      - name: 字节跳动校招
        scraper: bytedance
        domain: jobs.bytedance.com
        job_type: campus
        enabled: true

  - name: 腾讯
    sites:
      - name: 腾讯校招
        scraper: tencent
        domain: join.qq.com
        job_type: campus
        enabled: true
      - name: 腾讯社招
        scraper: tencent
        domain: careers.tencent.com
        job_type: social
        enabled: true

  - name: 影视飓风
    sites:
      - name: 影视飓风
        scraper: feishu
        domain: mediastorm.jobs.feishu.cn
        job_types: [social, campus]  # 一个网站支持多种类型
        enabled: true
```

### 配置字段说明

| 字段 | 说明 |
|-----|------|
| `name` (公司级) | 公司名称 |
| `sites` | 网站列表 |
| `sites[].name` | 网站名称 |
| `sites[].scraper` | 爬虫类型（feishu/bytedance/tencent 等） |
| `sites[].domain` | 招聘网站域名 |
| `sites[].job_type` | 单一类型（social/campus） |
| `sites[].job_types` | 多种类型列表（可选） |
| `sites[].enabled` | 是否启用该网站 |

## 支持的招聘类型

| 类型 | 标识 | 说明 |
|-----|------|------|
| 校招 | `campus` | 校园招聘 |
| 社招 | `social` | 社会招聘 |

## 已支持的招聘网站域名

| 公司 | 渠道 | 类型 | 完整 URL | 爬虫 |
|-----|------|------|---------|------|
| 字节跳动 | 字节跳动 | 社招 | https://jobs.bytedance.com/experienced/position | bytedance |
| 字节跳动 | 字节跳动 | 校招 | https://jobs.bytedance.com/campus/position | bytedance |
| 腾讯 | 腾讯 | 校招 | https://join.qq.com/post.html | tencent |
| 腾讯 | 腾讯 | 社招 | https://careers.tencent.com/search.html | tencent |
| 影视飓风 | 影视飓风 | 社招 | https://mediastorm.jobs.feishu.cn | feishu |

### 飞书招聘系统域名

飞书招聘系统被多家公司使用，域名格式通常为 `{公司标识}.jobs.feishu.cn`：

| 公司 | 域名 | 社招 | 校招 |
|-----|------|:----:|:----:|
| 影视飓风 | mediastorm.jobs.feishu.cn | ✓ | - |

> 如果你知道更多使用飞书招聘的公司域名，可以添加到配置文件中。

## 添加新爬虫

### 1. 创建爬虫文件

在 `scrapers/` 目录下创建 `newcompany.py`：

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
        # 实现爬取逻辑
        jobs = []
        # ...
        return jobs
```

### 2. 在 `__init__.py` 中导入

```python
from . import newcompany
```

### 3. 添加配置

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

## 命令参考

```bash
python main.py              # 交互式选择
python main.py quick        # 一键爬取所有
python main.py quick -t campus        # 仅校招
python main.py quick -t social        # 仅社招
python main.py quick -t campus,social # 校招+社招
python main.py crawl        # 交互式选择
python main.py init         # 初始化配置
python main.py config       # 查看配置
python main.py scrapers     # 列出爬虫
python main.py list         # 查看数据
```

## 项目结构

```
job-harvester/
├── config/
│   └── companies.yaml      # 公司配置
├── scrapers/
│   ├── __init__.py         # 模块入口
│   ├── base.py             # 基础爬虫类
│   ├── registry.py         # 爬虫注册器
│   ├── feishu.py           # 飞书招聘爬虫
│   ├── bytedance.py        # 字节跳动爬虫
│   └── tencent.py          # 腾讯招聘爬虫
├── storage/
│   └── csv_excel.py        # 数据存储
├── cli.py                  # 命令行接口
├── main.py                 # 程序入口
└── README.md
```

## 合规声明

> 本工具仅用于学习和研究目的，请遵守目标网站的 robots.txt 协议和使用条款。

## License

MIT