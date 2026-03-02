# JobHarvester - 招聘数据爬取工具

一个命令行工具，用于自动爬取使用飞书招聘系统的公司职位信息，支持 CSV/Excel 格式导出。

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 基本使用

```bash
# 方式 1：直接运行，进入交互式菜单（推荐）
python main.py

# 方式 2：交互式选择公司（空格键选择，回车确认）
python main.py crawl -i

# 方式 3：爬取配置中的所有公司
python main.py crawl --all

# 方式 4：爬取单家公司
python main.py crawl -c "影视飓风"

# 导出为 Excel 格式
python main.py crawl -c "影视飓风" -f excel

# 查看已保存的数据
python main.py list
```

### 输出目录

- **默认输出目录**: `./output/` 文件夹
- **未指定文件名**: 自动生成带时间戳的文件名（如 `jobs_20260302_143025.csv`）
- **自定义输出**: 使用 `-o` 指定文件名，使用 `-d` 指定目录

### 交互式菜单说明

直接运行 `python main.py` 后，会进入交互式菜单：

1. **选择公司**：使用 `↑` `↓` 键移动，`空格键` 选择/取消，`回车键` 确认
2. **输入文件名**：输入保存的文件名，默认 `jobs.csv`
3. **开始爬取**：自动爬取选中的公司并保存数据

支持多选，可以选择多家公司一次性爬取。

### 命令行帮助

```bash
python main.py --help
python main.py crawl --help
```

## 配置

编辑 `config/companies.yaml` 添加更多公司：

```yaml
companies:
  - name: 影视飓风
    domain: mediastorm.jobs.feishu.cn
    type: feishu
    enabled: true

  - name: 示例公司
    domain: example.jobs.feishu.cn
    type: feishu
    enabled: true
```

## 爬取字段

| 字段 | 说明 |
|-----|------|
| title | 职位名称 |
| company | 公司名称 |
| salary | 薪资范围 |
| location | 工作地点 |
| job_type | 职位类型（社招/校招/实习） |
| description | 职位描述 |
| url | 投递链接 |
| published_date | 发布时间 |

## 项目结构

```
job-harvester/
├── config/
│   └── companies.yaml      # 公司配置
├── scrapers/
│   ├── __init__.py
│   ├── base.py             # 基础爬虫类
│   └── feishu.py           # 飞书招聘爬虫
├── storage/
│   ├── __init__.py
│   └── csv_excel.py        # 数据存储
├── cli.py                  # 命令行接口
├── main.py                 # 程序入口
├── requirements.txt
└── README.md
```

## 版本历史

### v0.3.6 (当前版本)

- ✅ **默认输出目录**：新增 `output/` 文件夹作为默认输出目录
- ✅ **list 命令增强**：默认读取 `output/` 目录下的最新文件

### v0.3.5 (2026-03-02)

### v0.3.4 (2026-03-02)

### v0.3.3 (2026-03-02)

### v0.3.2 (2026-03-02)

### v0.2.0

- ✅ 支持爬取飞书招聘系统
- ✅ **自动翻页**：支持多页数据，自动获取全部职位
- ✅ CSV/Excel 格式导出
- ✅ **完整字段**：包含职位描述和职位要求
- ✅ **正确类型**：区分社招、校招、实习
- ✅ 现代化命令行接口
- ✅ 配置文件管理

### v0.1.0

- 初始版本
- 基础的飞书招聘爬取功能

## 合规声明

> **免责声明**：本工具仅用于学习和研究目的，请遵守目标网站的 robots.txt 协议和使用条款，不要进行高频爬取，避免对目标服务器造成负担。

## License

MIT
