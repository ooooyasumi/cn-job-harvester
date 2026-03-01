"""命令行接口"""
import typer
import asyncio
import yaml
import pandas as pd
import questionary
from pathlib import Path
from typing import Optional, List
from contextlib import contextmanager

from scrapers.feishu import FeishuScraper
from storage.csv_excel import JobStorage

app = typer.Typer(help="JobHarvester - 招聘数据爬取工具", invoke_without_command=True)


@contextmanager
def typer_context():
    """获取 typer context 的上下文管理器"""
    try:
        ctx = typer.Context(app)
        yield ctx
    except Exception:
        yield None


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
        output = "jobs.csv"
    else:
        output = questionary.text(
            "输入保存文件名 (默认：jobs.csv):",
            default="jobs.csv",
            style=questionary.Style()
        ).ask()

    if not output:
        output = "jobs.csv"

    # 如果没有扩展名，添加.csv
    if not output.endswith(('.csv', '.xlsx')):
        output += '.csv'

    all_jobs = []
    for company_config in selected:
        name = company_config['name']
        domain = company_config['domain']
        company_type = company_config.get('type', 'feishu')

        typer.echo(f"\n正在爬取：{name} ({domain})")

        if company_type == 'feishu':
            jobs = asyncio.run(_crawl_company(name, domain))
            all_jobs.extend(jobs)
            typer.echo(f"  爬取到 {len(jobs)} 个职位")

    if all_jobs:
        fmt = 'excel' if output.endswith('.xlsx') else 'csv'
        JobStorage.save(all_jobs, output, fmt)
        typer.echo(f"\n已保存 {len(all_jobs)} 个职位到 {output}")
    else:
        typer.echo("\n未爬取到任何职位数据")


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


@app.command("crawl")
def crawl(
    company: Optional[str] = typer.Option(None, "-c", "--company", help="公司名称"),
    all_companies: bool = typer.Option(False, "--all", help="爬取所有配置的公司"),
    output: str = typer.Option("jobs.csv", "-o", "--output", help="输出文件路径"),
    format: str = typer.Option("csv", "-f", "--format", help="输出格式：csv 或 excel"),
    interactive: bool = typer.Option(False, "-i", "--interactive", help="交互式选择公司"),
):
    """爬取招聘职位"""
    # 交互式模式
    if interactive or (not company and not all_companies):
        selected = _select_companies_interactive()
        if not selected:
            typer.echo("未选择任何公司")
            raise typer.Exit(0)
        all_companies = True  # 设置为全选模式处理

    if all_companies:
        # 加载配置文件
        config_path = Path(__file__).parent / "config" / "companies.yaml"
        if not config_path.exists():
            typer.echo(f"错误：配置文件不存在 {config_path}")
            raise typer.Exit(1)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        companies = [c for c in config.get('companies', []) if c.get('enabled', True)]
        typer.echo(f"发现 {len(companies)} 家启用的公司")

        all_jobs = []
        for company_config in companies:
            name = company_config['name']
            domain = company_config['domain']
            company_type = company_config.get('type', 'feishu')

            typer.echo(f"\n正在爬取：{name} ({domain})")

            if company_type == 'feishu':
                jobs = asyncio.run(_crawl_company(name, domain))
                all_jobs.extend(jobs)
                typer.echo(f"  爬取到 {len(jobs)} 个职位")

        # 保存所有数据
        if all_jobs:
            JobStorage.save(all_jobs, output, format)
            typer.echo(f"\n已保存 {len(all_jobs)} 个职位到 {output}")
        else:
            typer.echo("\n未爬取到任何职位数据")

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
        jobs = asyncio.run(_crawl_company(company, domain))
        typer.echo(f"爬取到 {len(jobs)} 个职位")

        if jobs:
            JobStorage.save(jobs, output, format)
            typer.echo(f"已保存到 {output}")
        else:
            typer.echo("未爬取到任何职位数据")


async def _crawl_company(company_name: str, domain: str):
    """爬取单家公司的职位"""
    scraper = FeishuScraper(company_name, domain)
    return await scraper.scrape()


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
    filepath: str = typer.Argument("jobs.csv", help="职位数据文件"),
):
    """查看已保存的职位数据"""
    path = Path(filepath)
    if not path.exists():
        typer.echo(f"文件不存在：{filepath}")
        raise typer.Exit(1)

    if filepath.endswith('.xlsx') or filepath.endswith('.xls'):
        df = pd.read_excel(filepath)
    else:
        df = pd.read_csv(filepath)

    typer.echo(f"\n共 {len(df)} 个职位:\n")

    for idx, row in df.iterrows():
        typer.echo(f"{idx + 1}. {row['title']} - {row['company']}")
        typer.echo(f"   薪资：{row['salary']} | 地点：{row['location']} | 类型：{row['job_type']}")
        typer.echo()


if __name__ == "__main__":
    app()
