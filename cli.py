"""命令行接口"""
import typer
import asyncio
import yaml
import pandas as pd
import questionary
from pathlib import Path
from typing import Optional, List
from contextlib import contextmanager
from datetime import datetime
import sys

from _version import __version__
from scrapers.feishu import FeishuScraper
from scrapers.bytedance import ByteDanceScraper
from storage.csv_excel import JobStorage

app = typer.Typer(help="JobHarvester - 招聘数据爬取工具", invoke_without_command=True)


@app.command("version")
def version():
    """显示版本号"""
    typer.echo(f"JobHarvester v{__version__}")

# 全局状态显示变量
_status_line = 0


def _print_status(message: str):
    """在命令行底部打印状态信息（使用回车符覆盖）"""
    # 使用 \r 覆盖当前行，\033[K 清除到行尾
    sys.stdout.write(f"\r\033[K{message}")
    sys.stdout.flush()


def _clear_status():
    """清除状态行"""
    sys.stdout.write("\r\033[K")
    sys.stdout.flush()


@contextmanager
def typer_context():
    """获取 typer context 的上下文管理器"""
    try:
        ctx = typer.Context(app)
        yield ctx
    except Exception:
        yield None


def _generate_filename(prefix: str = "jobs", extension: str = "csv") -> str:
    """生成带时间戳的文件名"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}.{extension}"


def _resolve_output_path(output: Optional[str], output_dir: Optional[str], format: str) -> str:
    """解析输出文件路径"""
    # 确定扩展名
    ext = "xlsx" if format == "excel" else "csv"

    # 如果指定了完整路径，直接使用
    if output:
        # 如果只有文件名没有路径，且指定了 output_dir，则组合
        if not Path(output).is_absolute() and output_dir:
            output_path = Path(output_dir) / output
        else:
            output_path = Path(output)

        # 确保目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 如果没有扩展名，添加扩展名
        if not output.endswith(('.csv', '.xlsx')):
            output_path = Path(str(output_path) + f".{ext}")
        return str(output_path)

    # 使用默认文件名（带时间戳）
    filename = _generate_filename("jobs", ext)

    # 如果指定了输出目录
    if output_dir:
        output_path = Path(output_dir) / filename
    else:
        output_path = Path(filename)

    # 确保目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return str(output_path)


@app.callback()
def callback(ctx: typer.Context):
    """JobHarvester - 招聘数据爬取工具"""
    if ctx.invoked_subcommand is None:
        # 没有子命令时，执行交互式模式
        _run_interactive_mode()


def _run_interactive_mode():
    """运行交互式模式"""
    import sys
    selected = _select_companies_interactive()
    if not selected:
        typer.echo("未选择任何公司")
        return

    typer.echo(f"\n已选择 {len(selected)} 家公司")
    for c in selected:
        typer.echo(f"  - {c['name']}")

    # 非终端环境使用默认文件名
    if not sys.stdin.isatty():
        output = _generate_filename("jobs")
    else:
        output = questionary.text(
            "输入保存文件名 (默认：jobs_时间戳.csv):",
            default=_generate_filename("jobs")
        ).ask()

    if not output:
        output = _generate_filename("jobs")

    # 如果没有扩展名，添加.csv
    if not output.endswith(('.csv', '.xlsx')):
        output += '.csv'

    typer.echo("按 Ctrl+C 可中断爬取并保存已获取的数据")

    all_jobs = []
    interrupted = False

    for idx, company_config in enumerate(selected, 1):
        name = company_config['name']
        domain = company_config['domain']
        company_type = company_config.get('type', 'feishu')

        # 定义状态回调
        def status_callback(msg, company=name, co=idx, total=len(selected)):
            _print_status(f"[{co}/{total}] {company}: {msg}")

        typer.echo(f"\n正在爬取：{name} ({domain})")

        try:
            if company_type == 'feishu':
                jobs = asyncio.run(_crawl_company(name, domain, 'feishu', status_callback))
            elif company_type == 'bytedance':
                jobs = asyncio.run(_crawl_company(name, domain, 'bytedance', status_callback))
            else:
                jobs = asyncio.run(_crawl_company(name, domain, 'feishu', status_callback))

            all_jobs.extend(jobs)
            _clear_status()
            typer.echo(f"  爬取到 {len(jobs)} 个职位")
        except KeyboardInterrupt:
            typer.echo("\n\n检测到 Ctrl+C 中断")
            interrupted = True
            break

    if all_jobs:
        fmt = 'excel' if output.endswith('.xlsx') else 'csv'
        JobStorage.save(all_jobs, output, fmt)
        typer.echo(f"\n已保存 {len(all_jobs)} 个职位到 {output}")
    else:
        typer.echo("\n未爬取到任何职位数据")

    if interrupted:
        raise typer.Exit(0)


def _load_companies() -> List[dict]:
    """加载配置文件中的公司列表"""
    config_path = Path(__file__).parent / "config" / "companies.yaml"
    if not config_path.exists():
        return []
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return [c for c in config.get('companies', []) if c.get('enabled', True)]


def _select_companies_interactive() -> List[dict]:
    """交互式选择公司"""
    import sys
    companies = _load_companies()
    if not companies:
        return []

    # 检查是否是真实终端
    if not sys.stdin.isatty():
        # 非终端环境，返回列表
        return companies

    print("\n=== 选择要爬取的公司 ===")
    print("提示：使用上下键移动，空格键选择/取消，回车键确认\n")

    choices = [
        questionary.Choice(title=f"{c['name']} ({c['domain']})", value=c)
        for c in companies
    ]
    # 添加全选选项
    choices.insert(0, questionary.Choice(title="[全选] 爬取所有配置的公司", value="ALL"))

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

    # 处理全选
    if "ALL" in selected:
        return companies

    return selected


@app.command("run")
def run(
    all_companies: bool = typer.Option(False, "--all", "-a", help="爬取所有配置的公司"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="输出文件名（默认：jobs_时间戳.csv）"),
    output_dir: Optional[str] = typer.Option(None, "-d", "--dir", help="输出目录（默认：当前目录）"),
    format: str = typer.Option("csv", "-f", "--format", help="输出格式：csv 或 excel"),
    interactive: bool = typer.Option(False, "-i", "--interactive", help="交互式选择公司"),
    max_pages: Optional[int] = typer.Option(None, "--max-pages", "-p", help="最大爬取页数（仅对字节跳动有效）"),
):
    """
    快速爬取模式 - 无需交互即可开始

    示例:
        # 爬取所有公司（默认）
        python main.py run

        # 爬取所有公司到指定目录
        python main.py run -d ./output

        # 爬取所有公司，导出为 Excel
        python main.py run -f excel

        # 交互式选择公司
        python main.py run -i
    """
    # 构建输出路径
    output_path = _resolve_output_path(output, output_dir, format)

    # 交互式模式
    if interactive:
        selected = _select_companies_interactive()
        if not selected:
            typer.echo("未选择任何公司")
            raise typer.Exit(0)
        all_companies = True  # 设置为全选模式处理

    if not all_companies:
        # 默认就是爬取所有
        all_companies = True

    # 爬取所有公司
    if all_companies:
        _crawl_all_companies(output_path, format, max_pages)


@app.command("quick")
def quick(
    output_dir: Optional[str] = typer.Option(None, "-d", "--dir", help="输出目录（默认：当前目录）"),
    format: str = typer.Option("csv", "-f", "--format", help="输出格式：csv 或 excel"),
    max_pages: Optional[int] = typer.Option(None, "--max-pages", "-p", help="最大爬取页数（仅对字节跳动有效）"),
):
    """
    一键爬取 - 最快速的爬取方式，爬取所有启用的公司

    示例:
        # 最简用法
        python main.py quick

        # 输出到指定目录
        python main.py quick -d ./data

        # 限制字节跳动爬取页数
        python main.py quick --max-pages 200
    """
    output_path = _resolve_output_path(None, output_dir, format)
    _crawl_all_companies(output_path, format, max_pages)


@app.command("crawl")
def crawl(
    company: Optional[str] = typer.Option(None, "-c", "--company", help="公司名称"),
    all_companies: bool = typer.Option(False, "--all", "-a", help="爬取所有配置的公司"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="输出文件名（默认：jobs_时间戳）"),
    output_dir: Optional[str] = typer.Option(None, "-d", "--dir", help="输出目录"),
    format: str = typer.Option("csv", "-f", "--format", help="输出格式：csv 或 excel"),
    interactive: bool = typer.Option(False, "-i", "--interactive", help="交互式选择公司"),
    max_pages: Optional[int] = typer.Option(None, "--max-pages", "-p", help="最大爬取页数（仅对字节跳动有效，默认爬取全部）"),
):
    """
    爬取招聘职位 - 灵活的爬取命令

    示例:
        # 爬取所有公司
        python main.py crawl --all

        # 爬取单家公司
        python main.py crawl -c "影视飓风"

        # 爬取到指定目录，使用自定义文件名
        python main.py crawl --all -d ./output -o myjobs.csv

        # 爬取所有公司，导出为 Excel
        python main.py crawl --all -f excel

        # 交互式选择
        python main.py crawl -i

        # 爬取字节跳动，限制 200 页
        python main.py crawl -c "字节跳动" --max-pages 200
    """
    # 构建输出路径
    output_path = _resolve_output_path(output, output_dir, format)

    # 交互式模式
    if interactive or (not company and not all_companies):
        selected = _select_companies_interactive()
        if not selected:
            typer.echo("未选择任何公司")
            raise typer.Exit(0)
        all_companies = True  # 设置为全选模式处理

    if all_companies:
        _crawl_all_companies(output_path, format, max_pages)

    elif company:
        # 爬取单家公司
        config_path = Path(__file__).parent / "config" / "companies.yaml"
        domain = None
        company_type = 'feishu'

        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            for c in config.get('companies', []):
                if c['name'] == company:
                    domain = c['domain']
                    company_type = c.get('type', 'feishu')
                    break

        if not domain:
            # 如果配置中没有找到，假设是飞书招聘
            typer.echo(f"警告：未在配置中找到 {company}，尝试使用飞书招聘格式")
            domain = f"{company}.jobs.feishu.cn"

        typer.echo(f"正在爬取：{company} ({domain})")
        typer.echo("按 Ctrl+C 可中断爬取并保存已获取的数据")

        # 定义状态回调
        def status_callback(msg):
            _print_status(f"{company}: {msg}")

        try:
            jobs = asyncio.run(_crawl_company(company, domain, company_type, status_callback, max_pages))
            _clear_status()
            typer.echo(f"\n爬取到 {len(jobs)} 个职位")
        except KeyboardInterrupt:
            typer.echo("\n\n检测到 Ctrl+C 中断")
            jobs = []  # 中断时可能没有返回值

        if jobs:
            JobStorage.save(jobs, output_path, format)
            typer.echo(f"已保存到 {output_path}")
        else:
            typer.echo("未爬取到任何职位数据")


def _crawl_all_companies(output_path: str, format: str, max_pages: int = None):
    """爬取所有配置的公司"""
    config_path = Path(__file__).parent / "config" / "companies.yaml"
    if not config_path.exists():
        typer.echo(f"错误：配置文件不存在 {config_path}")
        typer.echo("提示：使用 'python main.py init' 创建配置文件")
        raise typer.Exit(1)

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    companies = [c for c in config.get('companies', []) if c.get('enabled', True)]
    if not companies:
        typer.echo("错误：没有启用的公司配置")
        raise typer.Exit(1)

    typer.echo(f"发现 {len(companies)} 家启用的公司")
    typer.echo("按 Ctrl+C 可中断爬取并保存已获取的数据")

    all_jobs = []
    interrupted = False

    for idx, company_config in enumerate(companies, 1):
        name = company_config['name']
        domain = company_config['domain']
        company_type = company_config.get('type', 'feishu')

        # 定义状态回调
        def status_callback(msg, company=name, co=idx, total=len(companies)):
            _print_status(f"[{co}/{total}] {company}: {msg}")

        typer.echo(f"\n正在爬取：{name} ({domain})")

        try:
            if company_type == 'feishu':
                jobs = asyncio.run(_crawl_company(name, domain, 'feishu', status_callback, max_pages))
            elif company_type == 'bytedance':
                jobs = asyncio.run(_crawl_company(name, domain, 'bytedance', status_callback, max_pages))
            else:
                jobs = asyncio.run(_crawl_company(name, domain, 'feishu', status_callback, max_pages))

            all_jobs.extend(jobs)
            typer.echo(f"  爬取到 {len(jobs)} 个职位")
        except KeyboardInterrupt:
            typer.echo("\n\n检测到 Ctrl+C 中断")
            interrupted = True
            break

    _clear_status()

    # 保存所有数据（包括中断前的数据）
    if all_jobs:
        JobStorage.save(all_jobs, output_path, format)
        typer.echo(f"\n已保存 {len(all_jobs)} 个职位到 {output_path}")
    else:
        typer.echo("\n未爬取到任何职位数据")

    if interrupted:
        raise typer.Exit(0)


async def _crawl_company(company_name: str, domain: str, company_type: str = 'feishu', status_callback=None, max_pages: int = None):
    """爬取单家公司的职位

    Args:
        company_name: 公司名称
        domain: 域名
        company_type: 爬虫类型（feishu/bytedance）
        status_callback: 状态回调函数
        max_pages: 最大爬取页数（仅对字节跳动有效），None 表示爬取全部
    """
    if status_callback:
        status_callback(f"正在初始化爬虫...")
        await asyncio.sleep(0.1)

    if company_type == 'bytedance':
        scraper = ByteDanceScraper(company_name, domain, status_callback, max_pages)
    else:
        scraper = FeishuScraper(company_name, domain, status_callback)

    if status_callback:
        status_callback(f"正在爬取职位数据...")

    jobs = await scraper.scrape()

    if status_callback:
        status_callback(f"爬取完成，共 {len(jobs)} 个职位")
        await asyncio.sleep(0.3)

    return jobs


@app.command("init")
def init_config():
    """初始化配置文件"""
    config_path = Path(__file__).parent / "config" / "companies.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if config_path.exists():
        typer.echo(f"配置文件已存在：{config_path}")
        return

    default_config = """companies:
  - name: 影视飓风
    domain: mediastorm.jobs.feishu.cn
    type: feishu
    enabled: true

# 添加更多公司示例:
# - name: 示例公司
#   domain: example.jobs.feishu.cn
#   type: feishu
#   enabled: true
"""

    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(default_config)

    typer.echo(f"已创建配置文件：{config_path}")


@app.command("list")
def list_jobs(
    filepath: str = typer.Argument("jobs*.csv", help="职位数据文件路径（支持通配符）"),
    limit: int = typer.Option(20, "-l", "--limit", help="显示条数（默认 20）"),
):
    """查看已保存的职位数据"""
    from glob import glob

    # 支持通配符
    if '*' in filepath:
        files = glob(filepath)
        if not files:
            typer.echo(f"未找到匹配的文件：{filepath}")
            raise typer.Exit(1)
        # 使用最新的文件
        filepath = max(files, key=lambda p: Path(p).stat().st_mtime)
        typer.echo(f"使用最新文件：{filepath}")

    path = Path(filepath)
    if not path.exists():
        typer.echo(f"文件不存在：{filepath}")
        raise typer.Exit(1)

    if filepath.endswith('.xlsx') or filepath.endswith('.xls'):
        df = pd.read_excel(filepath)
    else:
        df = pd.read_csv(filepath)

    typer.echo(f"\n共 {len(df)} 个职位:\n")

    display_count = min(limit, len(df))
    for idx, row in df.head(display_count).iterrows():
        typer.echo(f"{idx + 1}. {row['title']} - {row['company']}")
        typer.echo(f"   薪资：{row['salary']} | 地点：{row['location']} | 类型：{row['job_type']}")
        typer.echo()

    if len(df) > limit:
        typer.echo(f"... 还有 {len(df) - limit} 条数据未显示（使用 -l 参数调整）")


@app.command("config")
def show_config():
    """查看当前配置"""
    config_path = Path(__file__).parent / "config" / "companies.yaml"
    if not config_path.exists():
        typer.echo("配置文件不存在")
        typer.echo("提示：使用 'python main.py init' 创建配置文件")
        raise typer.Exit(1)

    with open(config_path, 'r', encoding='utf-8') as f:
        content = f.read()

    typer.echo(f"配置文件：{config_path}")
    typer.echo("-" * 50)
    typer.echo(content)


if __name__ == "__main__":
    app()
