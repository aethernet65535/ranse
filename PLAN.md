# Ranse 重构实施说明（给实现 Agent）

> 本文档是**唯一实施依据**。所有架构决策已与维护者确认完毕，不要重新提出分层方案、
> 不要改动下列「已定决策」。按阶段推进，每阶段一个 commit，回归测试全绿才能进入下一阶段。

---

## 0. 背景与现状

Ranse 是给马来西亚教师用的 CLI 工具：读取周课表，自动填 e-RPH Excel 模板。
全部逻辑集中在 `scripts/fill-erph.py`（1231 行），混了 5 种职责：

| 现有代码段（行号） | 实际职责 |
|---|---|
| `_read_zip` / `_parse_sheet_rels` / `_parse_sheet_names` / `_read_shared_strings`（140–190） | xlsx 容器读写 |
| `_parse_sheet` / merge / row / cell / `write_cell` / `_set_cell_value`（196–337） | 单元格写入原语 |
| `read_csv` / `build_schedule` / `merge_periods` / `read_timetable_xlsx`（343–567） | 课表读取 + 领域模型 |
| `load_config` / `load_jadual_config` / `resolve_week` / `siri_to_timetable`（574–698） | 配置加载 + 周次解析 |
| `build_auto_dskp_entries` / `_section_pair` / `_dskp_file_for_tingkatan`（705–862） | 业务回调（周次滑动选 DSKP） |
| `fill_menu` / `write_fixed_cells` / `write_dskp_cells` / `fill_dskp_sheets`（869–1068） | 业务回调（写哪些格） |
| `main()`（1075–1231） | CLI 编排 |

配套文件：`scripts/constants.py`、`scripts/gen_dskp.py`（265 行）、
`scripts/erph-config.yaml`、`scripts/jadual-minggu.yaml`、`scripts/archived/preview-pdf.py`。

已知问题：
- `sys.exit()` / `print()` 散落 20+ 处，**包括本该是纯函数的 `resolve_week`、`siri_to_timetable`**；
- `load_dskp_content`、`build_auto_dskp_entries` 里 `sys.path.insert` + 动态 `import gen_dskp`；
- `_parse_sheet` 内有全局 `ET.register_namespace` 副作用；
- **没有任何测试**（`find . -name "test*"` 为空），只有 2 个 commit。

### ⚠️ 开工前必读：工作区有未提交改动

```
 M scripts/fill-erph.py   (+609/-…)      ← 大量未提交功能
 M scripts/erph-config.yaml
 M README.md  M .gitignore
 D scripts/{LICENSE,README.md,README.ms.md}   ← 已移动到根目录
?? scripts/gen_dskp.py  ?? scripts/jadual-minggu.yaml
```

**阶段 0 第一件事**：把这些收口成一个独立 commit，作为重构起点和 golden 基线来源。
基线必须取自**工作区当前状态**，不是 `HEAD`。否则重构 diff 与 WIP 混在一起，无法 review、无法回滚。

---

## 1. 已定决策（不要重新讨论）

| # | 项 | 决定 |
|---|---|---|
| 1 | Profile 形态 | **显式 `handlers:` 列表**（不采用「沿用旧顶层字段」或「两者兼容」） |
| 2 | Handler 发现 | **仅内置注册表**。不支持动态 import 路径，不支持 entry points 插件 |
| 3 | 打包 | **建可安装包，不留 `scripts/fill-erph.py` 旧入口**，README 全量更新 |
| 4 | 等价性验证 | **先写回归测试（golden）再动业务代码** |
| 5 | 附加范围 | dict→dataclass、README + `docs/translations/ms-MY/README.md` 更新、`gen_dskp.py` 收编 |
| 6 | **核心约束** | **业务逻辑不得进入核心**（core 里不出现 `DAY_ORDER`/`PERIOD_TIMES`/`BC-1A`/`minggu`/`cuti`/`sys.exit`） |
| 7 | core 读写边界 | core 对目标 workbook **只有写**：`open / sheet / write(coord, content) / save`。**不暴露 `read(coord)`**，需要时再加 |
| 8 | 输入读取归属 | 独立 **`inputs/` 层**（课表 xlsx/csv、DSKP txt/json、两份 YAML），不放 core，也不碰目标 workbook |
| 9 | `<coord> <write_content>` | **两层都要**：core Python API `wb.write("MENU!B3", "值")`；CLI 也提供 `ranse write` 单格子命令 |
| 10 | 模板路径 | **`--xlsx` 是 profile 专属参数**，写在 `profile.inputs.template`，不进 CLI |
| 11 | 校历文件 | `jadual-minggu.yaml` 是**独立数据文件**，由 profile 通过 `inputs.jadual` 引用，不并入 profile |
| 12 | 版面常量 | MENU 行 `5 + day_idx*10`、列 3–7、`NUM_PERIODS=8`、`CLASS_BLOCK_SIZE=31` 等**第一版留在 handler**，不进 profile |
| 13 | 错误处理（最小范围） | core 改为抛 `RanseError` 层级异常，由 CLI 统一转 exit code。**这是决策 6 的必要推论**。只改 core 的错误传递，**不做 logging 体系改造**，保持现有 `print(..., file=sys.stderr)` 风格于 CLI/handler 层 |

补充说明「读」的现状（维护者已确认）：
1. **读目标模板的单元格值** —— 不存在，也不需要（`_read_cell_value` 只服务于课表读取）；
2. **读输入课表** —— 必需，归 `inputs/`；
3. **读数据文件**（DSKP / profile / 校历）—— 必需，归 `inputs/`。

写入时读取 merge 区间和 `<c>` 的 `s=` 样式属性是为了**保持格式**，属结构元数据，不算值读取，留在 core。

---

## 2. 目标架构

```
┌─ CLI ──────────────────────────────────────────────┐
│  ranse fill  --profile p.yaml [--date][--minggu]   │  ← --xlsx 只在 profile 里
│  ranse write --profile p.yaml MENU!B3 "值"         │  ← 直接单格写
│  ranse dskp  --txt ... --select 1 1 1 -o out.json  │
└──────────────┬─────────────────────────────────────┘
               │ 只做编排 + 异常 → exit code
┌─ handlers/ ──▼─────────────────────────────────────┐
│  base.py       Resolver / Filler Protocol + Context│
│  registry.py   内置注册表（唯一发现方式）              │
│  week.py       校历 → minggu/siri/课表路径(cuti校验) │
│  menu.py       MENU 版面 + 时间后缀 + 连堂合并        │
│  fixed_cells.py / dskp.py   版面常量在此             │
└──────────────┬─────────────────────────────────────┘
               │ 只能调用 core 的 write API
┌─ core/ ──────▼──────────────┐  ┌─ inputs/ ──────────┐
│  Workbook.open()/save()     │  │  timetable.py 课表  │
│  sheet(name)                │  │  dskp.py  txt/json │
│  write(coord, content)      │  │  yaml.py profile/  │
│  merges（保格式所需结构）     │  │        校历加载     │
│  ✗ 不暴露 read(coord)        │  │  ✗ 不碰目标 workbook │
│  ✗ 无 DAY_ORDER/PERIOD_…    │  │                    │
└─────────────────────────────┘  └────────────────────┘
```

依赖方向严格单向：`cli → handlers → core`，`cli/handlers → inputs`。
**`core` 不得 import `handlers` 或 `inputs`。**

### 目标文件清单

```
pyproject.toml                       # [project] + console script + dev extra(pytest)
src/ranse/__init__.py
src/ranse/__main__.py                # python -m ranse
src/ranse/errors.py                  # RanseError / ProfileError / WeekError / SheetError
src/ranse/cli.py                     # argparse 子命令 + 两阶段编排 + 异常→exit code
src/ranse/core/__init__.py
src/ranse/core/refs.py               # A1 ↔ (row,col)、区域左上角、Excel 日期序列号
src/ranse/core/xlsx.py               # Workbook.open/save/sheet/write/merges
src/ranse/inputs/__init__.py
src/ranse/inputs/timetable.py        # read_csv / read_xlsx → Schedule
src/ranse/inputs/dskp.py             # ← gen_dskp.py 收编（含其 CLI main）
src/ranse/inputs/yaml.py             # profile + 校历加载与结构校验
src/ranse/handlers/__init__.py
src/ranse/handlers/base.py           # Resolver / Filler Protocol + Context dataclass
src/ranse/handlers/registry.py       # 内置注册表
src/ranse/handlers/{week,menu,fixed_cells,dskp}.py
src/ranse/model.py                   # Lesson / Schedule / Week dataclass + merge_periods
profiles/ali-bin-abu.yaml           # 显式 handlers 列表，含 inputs.template
config/jadual-minggu.yaml            # 独立校历（原 scripts/jadual-minggu.yaml）
tests/golden/                        # 基线 sheet XML（.gz，提交进 git）
tests/make_golden.py                 # 手工执行一次，生成基线
tests/test_core_refs.py
tests/test_handlers_menu.py
tests/test_week.py
tests/test_profile.py
tests/test_regression.py             # 依赖 assets/，缺失时 pytest.skip
README.md + docs/translations/ms-MY/README.md   # 结构/用法/配置三章重写

删除：scripts/ 整个目录（fill-erph.py、gen_dskp.py、constants.py、
      erph-config.yaml、jadual-minggu.yaml、archived/）
```

说明：
- `model.py` 放 `src/ranse/` 顶层而非 `core/`，因为 `Lesson/Schedule/Week` 携带
  `DAY_ORDER` 相关语义，属于领域模型，不属于纯写引擎；`inputs` 产出它、`handlers` 消费它。
  （若实现时更倾向 `core/model.py`，可接受，但**其中不得出现 e-RPH 版面知识**。）
- `assets/` 保持 `.gitignore`，**不作为 package data**。路径解析基准沿用现状：
  profile 所在目录 → cwd → 仓库根（复用现有 `_resolve_path`）。
- `requires-python = ">=3.9"`（dataclass + 现代打包）。README 现在写「Python 3.6+」，需一并改。
- `scripts/archived/preview-pdf.py`、`assets/timetable/src/*.jpg` 不在范围内，原样保留。

---

## 3. 接口草案

### core API（严格只有写）

```python
# src/ranse/core/xlsx.py
class Workbook:
    @classmethod
    def open(cls, path: str | Path) -> "Workbook": ...
    @property
    def sheets(self) -> list[str]: ...
    def sheet(self, name: str) -> "Sheet": ...
    def save(self, path: str | Path | None = None) -> None: ...   # None = 原地覆盖

class Sheet:
    def write(self, coord: str, content: str | int | float) -> None:
        """coord 形如 'B3' 或 'B3:C3'（取左上角，遵循合并单元格）。"""
    def merges(self) -> list[tuple[int, int, int, int]]: ...
```

要求：
- **不提供 `read(coord)`**。
- 写入时保留 `<c>` 上所有原属性（`s`/`t` 等），字符串写 `t="inlineStr"` + `<is><t>`，
  数字删 `t` 用 `<v>` —— 与现状 `_set_cell_value` 完全一致，**不得改变序列化结果**。
- 自动创建缺失的 `<row>` / `<c>` 并保持行列有序（现状 `_ensure_row` / `_ensure_cell` 逻辑）。
- `ET.register_namespace` 的副作用收进 `Workbook` 实例方法，不再全局散落
  —— 但**注册的前缀与 URI 必须与现状一字不差**，否则 golden 失败。

### Handler 接口（业务被接口本身挡在 core 外）

```python
# src/ranse/handlers/base.py
@dataclass
class Context:
    workbook: Workbook
    profile: Profile
    schedule: Schedule | None = None
    week: Week | None = None
    params: dict = field(default_factory=dict)   # 该 handler 自己的 params
    report: list[str] = field(default_factory=list)

class Resolver(Protocol):        # 阶段一：算出输入，不写格
    name: str
    def resolve(self, ctx: Context) -> None: ...

class Filler(Protocol):          # 阶段二：写格，只能通过 core
    name: str
    def fill(self, ctx: Context) -> list[str]: ...   # 返回 report 行
```

编排器 `cli.py` 的职责仅限：
`load profile → 建 Workbook → 跑全部 Resolver → (读课表，若需要) → 跑全部 Filler → save → 打印 report`。

### Profile schema（显式 handlers 列表）

```yaml
# profiles/ali-bin-abu.yaml
profile: ali-bin-abu-2026
inputs:
  template: "assets/ALI BIN ABU/12. ERPH/template.xlsx"   # --xlsx 专属位置
  jadual:   "config/jadual-minggu.yaml"                     # 独立校历，非 profile 本体

context:                        # 跨 handler 共享，禁止在 handler params 里复制两份
  subjects:
    BC: "BAHASA CINA 华 文"

handlers:
  - name: week                  # phase: resolve
  - name: menu                  # phase: fill
  - name: fixed_cells
    params:
      cells: [[MENU, "B3:C3", "ALI BIN ABU"]]
  - name: dskp
    params:
      mode: auto
      match_codes: [BC]
      match_names: ["BAHASA CINA", "华文"]
      cs: 1
      ls: 1
      left_col: 2
      right_col: 5
```

校验规则：未知 `name` → `ProfileError`；`params` 由各 handler 自己校验后报错；
`inputs.template` 缺失 → `ProfileError`。

### CLI

```
ranse fill  --profile profiles/ali-bin-abu.yaml [--date 2026-09-20] [--minggu 33] [--no-dskp-auto]
ranse write --profile profiles/ali-bin-abu.yaml MENU!B3 "ALI BIN ABU"
ranse dskp  --txt assets/bc-dskp/t1.txt [--select 1 1 1] [-o out.json] | [--pdf x.pdf --pages 35-45] | [--list]
```

- **没有 `--xlsx`**（决策 10）。
- `fill` 默认原地覆盖 `inputs.template`，与现状一致。
- 现有 `--config` / `--jadual-config` / `--timetable-xlsx` / `--csv` 的能力，
  全部由 profile 的 `inputs` 与 `handlers[].params` 承接；CLI 仅保留 `--date` / `--minggu` / `--no-dskp-auto` 作临时覆盖。
- 异常出口：`RanseError` → `print(f"Error: {e}", file=sys.stderr)` + `sys.exit(1)`；
  argparse 用法错误仍走 `parser.error`。

---

## 4. 分阶段实施

每阶段 = 一个 commit。**每阶段结束必须 `pytest` 全绿**，否则不得进入下一阶段。

### 阶段 0 —— 收口 WIP + 回归基线（不动业务代码）

1. 现有未提交改动单独 commit（`chore: 收口现有改动` 之类）。
2. 写 `tests/make_golden.py`，用**当前** `scripts/fill-erph.py` 跑出基线：
   - minggu 33（siri 1）、minggu 34（siri 7）两个正常周次；
   - 一个 `cuti` 周的**报错路径**（断言非零退出 + stderr 文案）；
   - 每次先把模板复制到临时目录再跑（脚本是原地覆盖）。
   - 基线存**逐 sheet 的 XML**（gzip），不存整个 zip —— zip 条目顺序/时间戳会造成假差异。
   - 存进 `tests/golden/<case>/<sheet>.xml.gz`，提交进 git。
3. 补纯函数单测（不依赖 `assets/`，新 clone 必须能跑）：
   `_col_to_num`/`_col_letter`/`_parse_cell_ref` 往返、`_cell_range_top_left`、
   `_date_to_excel`、`_section_pair` 滑动回绕（含最后一页 wrap）、
   `merge_periods`（连堂合并、时间不连续不合并）、`resolve_week`（含 cuti / 无 minggu / 越界日期）、
   `_parse_class_code`（`BC-1A`、`BC–1A` 全角连字符、非匹配原样返回）、
   `_time_with_suffix`（PAGI/TGH/TPTG 分界 11:00/14:00）。
4. 建 `pyproject.toml`（`[project]` + `dev` extra 含 pytest，`requires-python = ">=3.9"`）。
5. 依赖 `assets/` 的 `tests/test_regression.py` 在 assets 缺失时 `pytest.skip`。

**验收**：`pytest` 全绿；golden 已入库；WIP 已单独 commit。

### 阶段 1 —— 纯移动

只改 import 与文件归属，**不改任何逻辑、不改任何字符串、不改任何常量值**：

- 140–337 行 → `core/refs.py` + `core/xlsx.py`；
- 343–567 行 → `inputs/timetable.py`（`constants.PERIOD_TIMES`、`DAY_ORDER`、
  `DAY_BY_WEEKDAY`、`_TIME_SUFFIX_CACHE`、`NUM_PERIODS` 一并迁入 inputs 或 model）；
- `gen_dskp.py` → `inputs/dskp.py`（保留其 `main()`，阶段 4 接 CLI）；
- `load_config` / `load_jadual_config` → `inputs/yaml.py`；
- `fill_menu` / `write_fixed_cells` / `fill_dskp_*` / `build_auto_dskp_entries` /
  `resolve_week` / `siri_to_timetable` → 暂入 `handlers/`（先搬不改签名）；
- `main()` → `cli.py`。

**验收**：golden **逐字节相同**；纯函数单测不变全绿。

### 阶段 2 —— core 去业务化 + Handler 抽取

1. core 内所有 `sys.exit` / 业务文案 → `RanseError` 层级异常，由 `cli.py` 统一转 exit code
   （对应决策 13，**不要顺手引入 logging 框架**）。
2. 周次解析（`resolve_week` / `siri_to_timetable` / `load_jadual_config` 中的业务规则，
   含 cuti、无 minggu、日期越界文案）整体移入 `handlers/week.py`，实现 `Resolver`。
3. 逐个抽取 Filler，每个抽完跑一次 golden：
   `menu.py`（版面常量、`_time_with_suffix`、连堂合并、Excel 日期序列）→
   `fixed_cells.py`（合并区左上角 + `int(value)` 尝试转换）→
   `dskp.py`（`_section_pair` 滑动、`_dskp_file_for_tingkatan` 占位符、
   `CLASS_BLOCK_SIZE` 等版面常量、静态 selection 写入）。
4. 消灭 `sys.path.insert` + 动态 `import gen_dskp`，改为正常包内 import。
5. `_parse_sheet` 的 `ET.register_namespace` 副作用收进 `Workbook`。

**验收**：golden 逐字节相同；`grep -rn "sys.exit\|DAY_ORDER\|PERIOD_TIMES\|CLASS_BLOCK" src/ranse/core/` 无结果。

### 阶段 3 —— Profile schema + 两阶段编排 + dataclass

1. 新 profile 解析（显式 `handlers:` 列表、`inputs`、`context`），未知 handler 名报错。
2. `cli.py` 实现 resolve → 读课表 → fill → save 的两阶段编排。
3. 裸 dict → dataclass（`Lesson` / `Schedule` / `Week` / `Profile`）。
   **放在 handler 抽完之后做**，改动面最小；`entry["class"]` → `entry.class` 全量替换。
4. 写 `profiles/ali-bin-abu.yaml`，内容等价于现有 `erph-config.yaml` + `jadual-minggu.yaml` 引用。
5. `scripts/jadual-minggu.yaml` → `config/jadual-minggu.yaml`（文件内容除注释里的
   旧命令名外不变）。

**验收**：golden 逐字节相同；`tests/test_profile.py` 覆盖未知 handler、缺 template、
params 校验失败三种报错。

### 阶段 4 —— 打包 + CLI + 文档

1. `pyproject` 配 `[project.scripts] ranse = "ranse.cli:main"`；三个子命令落地。
2. 删除 `scripts/` 整个目录。
3. 重写 `README.md`：Project Structure、Installation（`pip install -e .`）、
   全部命令示例、Configuration 章节改为 Profile schema、Python 版本、
   「How It Works」保持原意。
4. `docs/translations/ms-MY/README.md` 同步（马来文，结构与英文版一致）。
5. `config/jadual-minggu.yaml` 顶部注释里的 `python fill-erph.py ...` 用法示例更新。

**验收**：`pip install -e .` 后 `ranse fill/write/dskp --help` 可用；
`grep -rn "fill-erph" . --exclude-dir=.git --exclude-dir=assets` 无残留（除 CHANGELOG/历史说明）；
golden 全绿。

---

## 5. 风险与坑（实现时逐条核对）

1. **序列化必须一字不差**：`xml_declaration=True, encoding="UTF-8", short_empty_elements=False`
   与所有 `register_namespace` 的前缀/URI 保持原样，否则 golden 全挂。
2. **golden 比 sheet XML，不比 zip 字节**。
3. **`subjects` 映射被 `fill_menu` 和 `dskp` 两处共用** → 放 profile `context:` 段共享，
   不要在两个 handler params 里复制两份。
4. **`PERIOD_TIMES` 存在两份**：`constants.py` 是 period→时间，`fill-erph.py` 顶部是
   时间→period（CSV 用）。合并到 `inputs/timetable.py` 一处，值不变。
5. **`assets/` 未入库** → 依赖真实模板的回归测试在新 clone 上 skip；
   纯函数单测必须完全自足，这是新 clone 上唯一的保护网。
6. **模板是 7.5MB 原地覆盖** → golden 生成脚本和回归测试都必须先 copy 到临时目录。
7. **`fill_menu` 会把空行写成 `""`**（清空上一次结果），抽 handler 时别把 else 分支删了。
8. **`fixed_cells` 的值有 `int(value)` 尝试转换**（`load_config` 阶段不做，
   在 `write_fixed_cells` 里做），迁移时保持时机一致，否则类型变化会让 golden 挂。
9. **`dskp_auto` 条目追加在静态 `dskp` 之后**（`cfg["dskp"] = static + auto`），
   同格时 auto 覆盖 static —— 顺序语义必须保留。
10. **Jumaat/Sabtu 课表会被丢弃**（模板只有 Ahad–Khamis 的 sheet），这是既有业务规则，
    属 `inputs/timetable.py` 或 handler，**不属于 core**。

---

## 6. 范围外（不要做）

- 不引入 `openpyxl`（README 明确以直接操作 XML 保格式为卖点）。
- 不做 logging 体系改造，不重构错误文案措辞。
- 不把版面常量下沉到 profile（决策 12）。
- 不支持 profile 动态加载第三方 handler（决策 2）。
- 不保留 `scripts/fill-erph.py` 兼容入口（决策 3）。
- 不改动 `assets/` 下任何文件，不动 `scripts/archived/preview-pdf.py`。
- 不新建额外的 plan/设计文档，本文件是唯一实施依据。
