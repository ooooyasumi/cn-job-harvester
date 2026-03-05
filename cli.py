"""命令行接口"""
import typer
import asyncio
import yaml
import pandas as pd
import questionary
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime
import sys

from _version import __version__
from scrapers import ScraperRegistry
from storage.csv_excel import JobStorage

app = typer.Typer(help="JobHarvester - 招聘数据爬取工具", invoke_without_command=True)

# 招聘类型定义
JOB_TYPES = {
    'campus': '校招',
    'social': '社招'
}


def _print_status(message: str):
    """在命令行底部打印状态信息"""
    sys.stdout.write(f"\r\033[K{message}")
    sys.stdout.flush()


def _clear_status():
    """清除状态行"""
    sys.stdout.write("\r\033[K")
    sys.stdout.flush()


def _generate_filename(prefix: str = "jobs", extension: str = "csv") -> str:
    """生成带时间戳的文件名"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}.{extension}"


def _resolve_output_path(output: Optional[str], output_dir: Optional[str], format: str) -> str:
    """解析输出文件路径"""
    ext = "xlsx" if format == "excel" else "csv"
    project_root = Path(__file__).resolve().parent

    if output:
        if not Path(output).is_absolute() and output_dir:
            output_path = Path(output_dir) / output
        elif not Path(output).is_absolute() and not output_dir:
            output_path = project_root / "output" / output
        else:
            output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not output.endswith(('.csv', '.xlsx')):
            output_path = Path(str(output_path) + f".{ext}")
        return str(output_path)

    filename = _generate_filename("jobs", ext)
    if output_dir:
        output_path = Path(output_dir) / filename
    else:
        output_path = project_root / "output" / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return str(output_path)


# ============== 配置加载模块 ==============

def load_config() -> Dict:
    """加载配置文件"""
    config_path = Path(__file__).parent / "config" / "companies.yaml"
    if not config_path.exists():
        return {'companies': []}
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {'companies': []}


def get_companies(config: Dict = None) -> List[Dict]:
    """获取公司列表"""
    if config is None:
        config = load_config()
    return config.get('companies', [])


def get_all_sites(companies: List[Dict] = None) -> List[Dict]:
    """获取所有网站

    配置结构：
    - site['domain']: 域名
    - site['path']: 路径（可选）
    - site['job_type']: 单一类型
    - 或 site['job_types']: 多种类型

    返回格式（每个网站只返回一次）:
    [
        {
            'company': '字节跳动',
            'site': '字节跳动社招',
            'scraper': 'bytedance',
            'domain': 'jobs.bytedance.com',
            'path': '/experienced/position',
            'job_types': ['social']
        },
        ...
    ]
    """
    if companies is None:
        companies = get_companies()

    sites = []
    for company in companies:
        company_name = company['name']
        for site in company.get('sites', []):
            if not site.get('enabled', True):
                continue

            site_name = site.get('name', company_name)
            scraper = site.get('scraper', 'feishu')
            domain = site.get('domain', '')
            path = site.get('path', '')

            # 处理类型：支持 job_type 或 job_types
            if 'job_types' in site:
                job_types = site['job_types']
            elif 'job_type' in site:
                job_types = [site['job_type']]
            else:
                job_types = ['social']

            if domain:
                sites.append({
                    'company': company_name,
                    'site': site_name,
                    'scraper': scraper,
                    'domain': domain,
                    'path': path,
                    'job_types': job_types
                })

    return sites


def filter_sites_by_type(sites: List[Dict], selected_type: str) -> List[Dict]:
    """根据选中的类型筛选网站"""
    return [s for s in sites if selected_type in s.get('job_types', [])]


def filter_sites_by_types(sites: List[Dict], selected_types: List[str]) -> List[Dict]:
    """根据选中的多个类型筛选网站（网站只返回一次）"""
    if not selected_types:
        return sites

    result = []
    seen = set()
    for s in sites:
        # 如果网站支持任一选中的类型，且未添加过
        key = f"{s['company']}_{s['site']}"
        if key not in seen:
            if any(t in s.get('job_types', []) for t in selected_types):
                result.append(s)
                seen.add(key)

    return result


# ============== 交互式选择模块 ==============

def interactive_select_types() -> List[str]:
    """交互式选择招聘类型"""
    if not sys.stdin.isatty():
        return list(JOB_TYPES.keys())

    print("\n=== 第一步：选择招聘类型 ===")
    print("提示：使用上下键移动，空格键选择/取消，回车键确认\n")

    choices = [
        questionary.Choice(
            title=f"{JOB_TYPES[jt]} ({jt})",
            value=jt
        )
        for jt in JOB_TYPES.keys()
    ]
    choices.insert(0, questionary.Choice(title="[全选] 选择所有类型", value="ALL"))

    selected = questionary.checkbox(
        "",
        choices=choices,
        style=questionary.Style([
            ('checkbox-selected', 'fg:green bold'),
            ('selected', 'fg:green bold'),
            ('pointer', 'fg:green bold'),
            ('highlighted', 'fg:green bold'),
        ])
    ).ask()

    if not selected:
        return []

    if "ALL" in selected:
        return list(JOB_TYPES.keys())

    return selected


def interactive_select_sites(sites: List[Dict]) -> List[Dict]:
    """交互式选择网站（每个网站只显示一次）"""
    if not sys.stdin.isatty():
        return sites

    if not sites:
        print("没有符合条件的招聘网站")
        return []

    print("\n=== 第二步：选择公司和网站 ===")
    print("提示：使用上下键移动，空格键选择/取消，回车键确认\n")

    choices = []
    for s in sites:
        # 显示网站支持的所有类型
        type_labels = [JOB_TYPES.get(t, t) for t in s.get('job_types', [])]
        type_str = '/'.join(type_labels)
        title = f"{s['company']} - {s['site']} ({type_str})"
        choices.append(questionary.Choice(title=title, value=s))

    choices.insert(0, questionary.Choice(title="[全选] 选择所有网站", value="ALL"))

    selected = questionary.checkbox(
        "",
        choices=choices,
        style=questionary.Style([
            ('checkbox-selected', 'fg:green bold'),
            ('selected', 'fg:green bold'),
            ('pointer', 'fg:green bold'),
            ('highlighted', 'fg:green bold'),
        ])
    ).ask()

    if not selected:
        return []

    if "ALL" in selected:
        return sites

    return selected


def interactive_select() -> List[Dict]:
    """完整的交互式选择流程"""
    # 第一步：选择类型
    selected_types = interactive_select_types()
    if not selected_types:
        return []

    # 获取所有网站并筛选
    all_sites = get_all_sites()
    filtered_sites = filter_sites_by_types(all_sites, selected_types)

    # 第二步：选择网站
    return interactive_select_sites(filtered_sites)


# ============== 爬取模块 ==============

async def crawl_single_site(
    site: Dict,
    selected_types: List[str] = None,
    status_callback=None,
    max_pages: int = None
) -> List:
    """爬取单个网站

    Args:
        site: 网站配置
        selected_types: 选中的类型列表，用于筛选爬取的职位
        status_callback: 状态回调
        max_pages: 最大页数
    """
    company_name = site['company']
    domain = site['domain']
    scraper_type = site['scraper']

    if status_callback:
        status_callback("正在初始化爬虫...")
        await asyncio.sleep(0.1)

    scraper_class = ScraperRegistry.get(scraper_type)
    if not scraper_class:
        raise ValueError(f"未知的爬虫类型: {scraper_type}")

    scraper = scraper_class(
        company_name=company_name,
        domain=domain,
        status_callback=status_callback,
        max_pages=max_pages
    )

    if status_callback:
        status_callback("正在爬取职位数据...")

    jobs = await scraper.scrape()

    # 根据选中的类型筛选职位
    if selected_types:
        type_names = [JOB_TYPES.get(t, t) for t in selected_types]
        jobs = [j for j in jobs if j.job_type in type_names]

    if status_callback:
        status_callback(f"爬取完成，共 {len(jobs)} 个职位")
        await asyncio.sleep(0.3)

    return jobs


def crawl_sites(sites: List[Dict], selected_types: List[str], output_path: str, format: str, max_pages: int = None):
    """爬取多个网站"""
    typer.echo(f"\n发现 {len(sites)} 个招聘网站")
    typer.echo("按 Ctrl+C 可中断爬取并保存已获取的数据")

    all_jobs = []
    interrupted = False

    for idx, site in enumerate(sites, 1):
        company_name = site['company']
        site_name = site['site']

        # 显示网站支持的所有类型
        type_labels = [JOB_TYPES.get(t, t) for t in site.get('job_types', [])]
        type_str = '/'.join(type_labels)

        def status_callback(msg, co=idx, total=len(sites)):
            _print_status(f"[{co}/{total}] {company_name}-{site_name}: {msg}")

        typer.echo(f"\n正在爬取：{company_name} - {site_name} ({type_str})")

        try:
            jobs = asyncio.run(crawl_single_site(site, selected_types, status_callback, max_pages))
            all_jobs.extend(jobs)
            typer.echo(f"  爬取到 {len(jobs)} 个职位")
        except KeyboardInterrupt:
            typer.echo("\n\n检测到 Ctrl+C 中断")
            interrupted = True
            break

    _clear_status()

    if all_jobs:
        JobStorage.save(all_jobs, output_path, format)
        typer.echo(f"\n已保存 {len(all_jobs)} 个职位到 {output_path}")
    else:
        typer.echo("\n未爬取到任何职位数据")

    if interrupted:
        raise typer.Exit(0)


# ============== 命令定义 ==============

@app.command("version")
def version():
    """显示版本号"""
    typer.echo(f"JobHarvester v{__version__}")


@app.callback()
def callback(ctx: typer.Context):
    """JobHarvester - 招聘数据爬取工具"""
    if ctx.invoked_subcommand is None:
        _run_interactive_mode()


def _run_interactive_mode():
    """运行交互式模式"""
    selected_types = interactive_select_types()
    if not selected_types:
        typer.echo("未选择任何类型")
        return

    all_sites = get_all_sites()
    filtered_sites = filter_sites_by_types(all_sites, selected_types)

    selected = interactive_select_sites(filtered_sites)
    if not selected:
        typer.echo("未选择任何网站")
        return

    typer.echo(f"\n已选择 {len(selected)} 个网站")
    for s in selected:
        type_labels = [JOB_TYPES.get(t, t) for t in s.get('job_types', [])]
        type_str = '/'.join(type_labels)
        typer.echo(f"  - {s['company']} - {s['site']} ({type_str})")

    # 输入文件名
    if not sys.stdin.isatty():
        output = _resolve_output_path(None, None, 'csv')
    else:
        user_input = questionary.text(
            "输入保存文件名 (默认：jobs_时间戳.csv):",
            default=_generate_filename("jobs")
        ).ask() or _generate_filename("jobs")

        if not user_input.endswith(('.csv', '.xlsx')):
            user_input += '.csv'
        output = _resolve_output_path(user_input, None, 'csv')

    typer.echo("\n按 Ctrl+C 可中断爬取并保存已获取的数据")
    crawl_sites(selected, selected_types, output, 'csv')


@app.command("quick")
def quick(
    output_dir: Optional[str] = typer.Option(None, "-d", "--dir", help="输出目录"),
    format: str = typer.Option("csv", "-f", "--format", help="输出格式：csv 或 excel"),
    types: Optional[str] = typer.Option(None, "-t", "--types", help="招聘类型，逗号分隔：campus,social"),
    max_pages: Optional[int] = typer.Option(None, "-p", "--max-pages", help="最大爬取页数"),
):
    """一键爬取所有启用的网站

    示例:
        python main.py quick
        python main.py quick -t campus
        python main.py quick -t social,campus
    """
    output_path = _resolve_output_path(None, output_dir, format)

    all_sites = get_all_sites()

    # 解析类型筛选
    selected_types = None
    if types:
        selected_types = [t.strip() for t in types.split(',')]
        all_sites = filter_sites_by_types(all_sites, selected_types)

    if not all_sites:
        typer.echo("没有符合条件的招聘网站")
        raise typer.Exit(0)

    if not selected_types:
        selected_types = list(JOB_TYPES.keys())

    crawl_sites(all_sites, selected_types, output_path, format, max_pages)


@app.command("crawl")
def crawl(
    output: Optional[str] = typer.Option(None, "-o", "--output", help="输出文件名"),
    output_dir: Optional[str] = typer.Option(None, "-d", "--dir", help="输出目录"),
    format: str = typer.Option("csv", "-f", "--format", help="输出格式"),
    max_pages: Optional[int] = typer.Option(None, "-p", "--max-pages", help="最大爬取页数"),
):
    """交互式爬取 - 先选类型再选网站

    示例:
        python main.py crawl
    """
    selected_types = interactive_select_types()
    if not selected_types:
        typer.echo("未选择任何类型")
        raise typer.Exit(0)

    all_sites = get_all_sites()
    filtered_sites = filter_sites_by_types(all_sites, selected_types)

    selected = interactive_select_sites(filtered_sites)
    if not selected:
        typer.echo("未选择任何网站")
        raise typer.Exit(0)

    output_path = _resolve_output_path(output, output_dir, format)
    crawl_sites(selected, selected_types, output_path, format, max_pages)


@app.command("init")
def init_config():
    """初始化配置文件"""
    config_path = Path(__file__).parent / "config" / "companies.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if config_path.exists():
        typer.echo(f"配置文件已存在：{config_path}")
        return

    default_config = """# 公司招聘配置
#
# 配置结构说明：
#   - 类型（job_type）：校招(campus)、社招(social)
#   - 公司（company）：字节、腾讯等
#   - 网站（site）：每个网站独立配置
#     - job_type: 单一类型
#     - job_types: 多种类型（一个网站同时支持校招和社招）
#
# 选择流程：先选类型 → 再选公司-网站

companies:
  - name: 字节跳动
    sites:
      - name: 字节跳动社招
        scraper: bytedance
        domain: jobs.bytedance.com
        path: /experienced/position
        job_type: social
        enabled: true
      - name: 字节跳动校招
        scraper: bytedance
        domain: jobs.bytedance.com
        path: /campus/position
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
        job_types: [social, campus]  # 同时支持社招和校招
        enabled: true
"""

    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(default_config)

    typer.echo(f"已创建配置文件：{config_path}")


@app.command("config")
def show_config():
    """查看当前配置"""
    config_path = Path(__file__).parent / "config" / "companies.yaml"
    if not config_path.exists():
        typer.echo("配置文件不存在，使用 'python main.py init' 创建")
        raise typer.Exit(1)

    with open(config_path, 'r', encoding='utf-8') as f:
        content = f.read()

    typer.echo(f"配置文件：{config_path}")
    typer.echo("-" * 50)
    typer.echo(content)


@app.command("scrapers")
def list_scrapers():
    """列出所有已注册的爬虫"""
    scrapers = ScraperRegistry.list()
    if not scrapers:
        typer.echo("没有已注册的爬虫")
        return

    typer.echo("已注册的爬虫类型：")
    for s in scrapers:
        scraper_class = ScraperRegistry.get(s)
        doc = scraper_class.__doc__ or ""
        typer.echo(f"  - {s}: {doc.strip().split(chr(10))[0] if doc else '无描述'}")


@app.command("list")
def list_jobs(
    filepath: Optional[str] = typer.Argument(None, help="职位数据文件路径"),
    limit: int = typer.Option(20, "-l", "--limit", help="显示条数"),
):
    """查看已保存的职位数据"""
    from glob import glob

    project_root = Path(__file__).resolve().parent
    default_output_dir = project_root / "output"

    if filepath is None:
        if not default_output_dir.exists():
            typer.echo("output 目录不存在")
            raise typer.Exit(1)
        files = glob(str(default_output_dir / "jobs*.csv")) + glob(str(default_output_dir / "jobs*.xlsx"))
        if not files:
            typer.echo("output 目录没有找到文件")
            raise typer.Exit(1)
        filepath = max(files, key=lambda p: Path(p).stat().st_mtime)
        typer.echo(f"使用最新文件：{filepath}")

    if '*' in filepath:
        files = glob(filepath)
        if not files:
            typer.echo(f"未找到匹配的文件：{filepath}")
            raise typer.Exit(1)
        filepath = max(files, key=lambda p: Path(p).stat().st_mtime)

    path = Path(filepath)
    if not path.exists():
        typer.echo(f"文件不存在：{filepath}")
        raise typer.Exit(1)

    df = pd.read_excel(filepath) if filepath.endswith(('.xlsx', '.xls')) else pd.read_csv(filepath)

    typer.echo(f"\n共 {len(df)} 个职位:\n")
    for idx, row in df.head(min(limit, len(df))).iterrows():
        typer.echo(f"{idx + 1}. {row['title']} - {row['company']}")
        typer.echo(f"   薪资：{row['salary']} | 地点：{row['location']} | 类型：{row['job_type']}")
        typer.echo()

    if len(df) > limit:
        typer.echo(f"... 还有 {len(df) - limit} 条数据未显示")


if __name__ == "__main__":
    app()