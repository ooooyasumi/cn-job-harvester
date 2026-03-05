# 更新日志

## v0.5.0 (2026-03-05)

### 架构重构

#### 模块化架构 - 注册器模式
- 新增 `ScraperRegistry` 注册器，添加新爬虫只需创建文件并添加装饰器
- 统一爬虫基类 `BaseScraper`，提供 `progress()`, `progress_with_eta()`, `done()` 方法
- 所有爬虫使用统一的状态回调，移除了各爬虫中的 `print()` 语句

#### 配置结构优化
- 三层配置结构：公司 -> 渠道 -> 类型（校招/社招）
- 支持每个公司配置多个招聘渠道（如淘天集团、千问团队等）
- 简化招聘类型：仅保留校招和社招

#### 交互式选择流程
- 第一步：多选招聘类型（校招/社招）
- 第二步：多选公司-渠道
- 支持全选快捷操作

#### 腾讯爬虫优化
- 根据域名自动判断爬取类型：
  - `join.qq.com` → 校招
  - `careers.tencent.com` → 社招

### 使用示例

```bash
# 交互式选择
python main.py

# 一键爬取所有
python main.py quick

# 仅爬取校招
python main.py quick -t campus

# 仅爬取社招
python main.py quick -t social
```

### 添加新爬虫

现在只需 3 步：

1. 创建爬虫文件 `scrapers/newcompany.py`：
```python
@ScraperRegistry.register('newcompany')
class NewCompanyScraper(BaseScraper):
    async def scrape(self) -> List[Job]:
        # 核心爬取逻辑
        pass
```

2. 在 `scrapers/__init__.py` 添加导入

3. 在 `config/companies.yaml` 添加配置

---

## v0.4.0 (2026-03-02)

### 性能优化

#### 字节跳动爬虫 8 倍提速
- **优化前**: 爬取全部 1771 页约需 90 分钟
- **优化后**: 爬取全部 1771 页约需 11 分钟

**优化措施**:
1. **资源加载优化**: 禁用图片、字体、CSS 等资源加载（减少 50% 流量）
2. **页面加载状态**: 使用 `domcontentloaded` 而非 `networkidle`（减少等待时间）
3. **翻页延迟优化**: 1.5 秒 → 0.3 秒
4. **批次大小优化**: 100 页 → 500 页
5. **批次休息优化**: 3 秒 → 0.5 秒
6. **初始等待优化**: 2 秒 → 0.5 秒

**性能对比**:
| 页数 | 优化前时间 | 优化后时间 |
|------|-----------|-----------|
| 50 页 | ~90 秒 | ~25 秒 |
| 200 页 | ~6 分钟 | ~76 秒 |
| 1771 页（全程） | ~90 分钟 | ~11 分钟 |

---

## v0.3.9 (2026-03-02)

### 功能优化

#### 腾讯爬虫全量爬取支持
- 移除了 50 页的默认限制
- 现在默认爬取全部职位（约 258 页/2580+ 个岗位）
- 可通过 `--max-pages` 参数手动限制页数

**使用示例**:
```bash
# 爬取所有腾讯职位（2580+ 个）
python main.py crawl -c "腾讯"

# 限制爬取页数
python main.py crawl -c "腾讯" --max-pages 100
```

---

## v0.3.8 (2026-03-02)

### Bug 修复

#### 腾讯爬虫类型处理修复
- **问题**: 在交互式模式和 `crawl` 命令中，腾讯爬虫类型未被正确处理，导致使用飞书爬虫而非腾讯爬虫
- **原因**: `cli.py` 中的条件判断缺少 `tencent` 分支，落入 `else` 使用了错误的爬虫
- **修复**: 在 `_run_interactive_mode()` 和 `_crawl_all_companies()` 中添加 `tencent` 类型处理

**受影响的功能**:
- `python main.py` (交互式模式)
- `python main.py crawl --all`
- `python main.py run`

**修复前**: 腾讯职位爬取失败，显示 "API 获取失败"
**修复后**: 腾讯职位正常爬取（校招 + 社招）

### 代码改进

#### cli.py
- 为未知公司类型添加警告提示
- 为交互式模式添加 `max_pages` 变量定义
- 统一所有爬虫调用传递 `max_pages` 参数

---

## v0.3.7 (2026-03-02)

### 新增功能

#### 腾讯招聘爬虫支持
- 支持爬取腾讯招聘（https://join.qq.com 和 https://careers.tencent.com）
- 同时爬取校招/实习和社招两类职位
- 校招/实习：从 join.qq.com 获取
- 社招：从 careers.tencent.com 获取，支持翻页爬取

**使用示例**:
```bash
# 爬取腾讯职位
python main.py crawl -c "腾讯"

# 限制爬取页数
python main.py crawl -c "腾讯" --max-pages 10
```

**爬取字段**:
- 校招/实习：职位名称、地点、事业群、类型（应届/实习）
- 社招：职位名称、地点、职责描述、发布时间、投递链接

---

## v0.3.6 (2026-03-02)

### 新增功能

#### 默认输出目录
- 新增 `output/` 文件夹作为默认输出目录
- 未指定 `-o` 参数时，文件自动保存到 `./output/jobs_时间戳.csv`
- `list` 命令默认读取 `output/` 目录下的最新文件

### 使用示例
```bash
# 爬取并自动保存到 output/jobs_时间戳.csv
python main.py crawl -c "字节跳动"

# 查看 output 目录最新文件
python main.py list

# 查看指定文件
python main.py list output/jobs_20260302_120000.csv
```

---

## v0.3.5 (2026-03-02)

### 新增功能

#### 导出表格添加序号
- CSV 和 Excel 导出的表格在第一列添加"序号"列
- 序号从 1 开始递增

#### 进度显示增强
- 显示当前页数/总页数
- 显示百分比进度
- 显示已获取职位数量
- 显示预计剩余时间（ETA）

**示例输出**:
```
进度：50/1000 (5.0%) | 已获 500 职位 | 预计剩余：45 分钟
```

#### Ctrl+C 中断保存
- 爬取过程中按 Ctrl+C 可中断
- 自动保存已爬取的职位数据
- 不会丢失已获取的数据

### 使用示例
```bash
# 爬取字节跳动，显示完整进度
python main.py crawl -c "字节跳动" -o bytedance.csv

# 爬取过程中按 Ctrl+C 可中断并保存
# 已获取的数据会自动保存到输出文件
```

### 技术细节

#### 进度信息格式
```
进度：{current_page}/{total_pages} ({percent}%) | 已获 {jobs} 职位 | 预计剩余：{eta}
```

#### ETA 计算
- 根据已爬取页数和耗时计算平均每页时间
- 剩余页数 × 平均每页时间 = 预计剩余时间
- 时间格式自动适配（秒/分钟/小时）

---

## v0.3.4 (2026-03-02)

### 重大修复：字节跳动爬虫全量爬取支持

#### 问题描述
- 字节跳动社招约 1000 页（10000 个职位），校招约 771 页（7700 个职位），总计约 17000 个职位
- 之前版本只爬取 50 页（约 500 个职位），遗漏了大量数据

#### 修复方案
- 移除 50 页限制，默认爬取全部页面
- 添加批量爬取机制：每 100 页为一批，批次间休息 3 秒，防止被反爬
- 添加 `--max-pages` 参数，用户可自定义最大爬取页数
- 优化状态显示，显示当前进度（第 X/总页数 页）

#### 使用示例
```bash
# 爬取全部职位（默认）
python main.py crawl -c "字节跳动" -o bytedance.csv

# 限制爬取 200 页（约 2000 个职位）
python main.py crawl -c "字节跳动" --max-pages 200

# 爬取全部社招 + 校招（约 17000 个职位，耗时约 60-90 分钟）
python main.py crawl -c "字节跳动" -o bytedance_full.csv
```

#### 爬取时间估算
| 页数 | 职位数 | 预计时间 |
|------|--------|----------|
| 50 页 | ~500 | ~2 分钟 |
| 200 页 | ~2000 | ~10 分钟 |
| 500 页 | ~5000 | ~25 分钟 |
| 1000 页 | ~10000 | ~50 分钟 |
| 全部（1771 页） | ~17000 | ~90 分钟 |

---

## v0.3.3 (2026-03-02)

### 重大修复：字节跳动爬虫翻页功能

#### 问题描述
- **现象**：字节跳动爬虫只爬取到 40 个职位，但实际有上万个职位
- **根本原因**：
  1. `_goto_next_page()` 方法查找"下一页"文本的按钮，但字节跳动使用页码数字（1, 2, 3...）
  2. 翻页逻辑错误，导致无法正确点击页码
  3. 爬取校招数据前未清空 API 响应列表

#### 修复方案
- 新增 `_get_page_count()` 方法，获取总页数
- 新增 `_goto_page(page_num)` 方法，直接点击指定页码
- 修改 `_collect_jobs_with_pagination()` 方法：
  - 先获取总页数
  - 使用 `_goto_page()` 逐页翻页
  - 最大爬取 50 页（约 500 个职位），避免爬取时间过长
- 在爬取校招数据前清空 `self._api_responses`

#### 修复效果
- **修复前**：仅爬取约 40 个职位
- **修复后**：爬取约 900+ 个职位（社招 500 + 校招 500）
- 社招链接正确包含 `/experienced/position/detail/`
- 校招链接正确包含 `/campus/position/detail/`

---

## v0.3.2 (2026-03-02)

### 新增功能

#### 实时状态显示
- 在命令行爬取界面底部添加动态状态行
- 显示当前爬取进度，包括：
  - 浏览器启动状态
  - 页面访问状态
  - 翻页进度（第 X 页）
  - 数据获取数量
  - 数据处理状态
- 使用 `\r` 和 ANSI 转义序列实现快速刷新，不污染输出

**示例输出**:
```
[1/2] 字节跳动：正在翻到第 3 页...
[1/2] 字节跳动：获取到 45 个职位
[2/2] 字节跳动：解析 89 个职位数据...
```

### Bug 修复

#### 字节跳动链接修复
- **问题**：字节跳动爬虫输出的职位链接无法打开，缺少 `/campus/` 或 `/experienced/` 路径前缀
- **原因**：当前实现将校招和社招视为一个公司，但链接生成时无法区分类型
- **修复方案**：
  - 修改 `ByteDanceScraper._collect_jobs_with_pagination()` 方法，接收 `job_type` 参数
  - 修改 `ByteDanceScraper._parse_job_posts()` 方法，接收并使用类型参数
  - 修改 `ByteDanceScraper.get_job_url()` 方法，根据类型生成正确链接

**修复前链接**:
```
https://jobs.bytedance.com/position/detail/7600300955226589493  # 无法打开
```

**修复后链接**:
```
https://jobs.bytedance.com/campus/position/detail/7600300955226589493     # 校招
https://jobs.bytedance.com/experienced/position/detail/7600300955226589493  # 社招
```

### 代码变更

| 文件 | 修改内容 |
|------|----------|
| `cli.py` | 添加 `_print_status()` 和 `_clear_status()` 状态显示函数<br>修改 `_crawl_company()` 添加 `status_callback` 参数<br>修改 `_crawl_all_companies()` 和 `_run_interactive_mode()` 使用状态回调 |
| `scrapers/bytedance.py` | 构造函数添加 `status_callback` 参数<br>`scrape()` 方法添加详细状态显示<br>`_collect_jobs_with_pagination()` 添加 `job_type` 参数和状态显示<br>`_parse_job_posts()` 添加 `job_type` 参数<br>`get_job_url()` 添加 `job_type` 参数，根据类型生成正确前缀 |
| `scrapers/feishu.py` | 构造函数添加 `status_callback` 参数<br>`scrape()` 方法添加详细状态显示 |

### 技术细节

#### 状态显示实现
```python
def _print_status(message: str):
    """在命令行底部打印状态信息（使用回车符覆盖）"""
    sys.stdout.write(f"\r\033[K{message}")
    sys.stdout.flush()
```

#### 链接生成实现
```python
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
```

### 测试建议

```bash
# 测试字节跳动爬取
python main.py crawl -c "字节跳动" -o test_bytedance.csv

# 检查链接格式
python main.py list test_bytedance.csv -l 5

# 测试状态显示
python main.py crawl --all
```

---

## v0.2.0

- 支持爬取飞书招聘系统
- 自动翻页功能
- CSV/Excel 格式导出
- 完整字段输出
- 正确区分社招、校招、实习类型

## v0.1.0

- 初始版本
- 基础的飞书招聘爬取功能

---

## 版本计划

### v0.4.0（已完成）✅
- ✅ 性能优化（字节跳动爬虫 8 倍提速）

### v0.5.0（已完成）✅
- ✅ 模块化架构重构（注册器模式）
- ✅ 统一进度显示接口
- ✅ 多渠道配置支持

### v0.6.0（短期）
- 增量更新功能（基于职位 ID 去重）
- 错误处理和重试机制
- 更多招聘系统支持（北森、Moka）

### v1.0.0（长期）
- 完整的单元测试（覆盖率 > 80%）
- 详细的使用文档（Sphinx）
- PyPI 发布
- Docker 镜像
- CI/CD 配置
