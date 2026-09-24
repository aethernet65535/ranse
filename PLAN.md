# PLAN — 插件化重组 + 全仓英文化（framework / plugins 分层）

> **状态：需求已定稿，待开工**。分 4 阶段执行；每阶段 `pytest` 全绿 + golden
> 字节不变 + 单独提交。
> 前一份计划（core/CLI/inputs 去业务化，6 阶段）已完成，止于提交 `bb57dd7`；
> 其后追加提交 `55a31be`（顶层移除 `ranse dskp`，注册表清空）。

## 目标

1. **framework 零业务**：`src/ranse/` 不再承载任何业务——词汇、类型、
   注册表、目录皆然；CI 词汇扫描覆盖**整个包、白名单清零**。
2. **业务 = 插件**：handler、profile、业务 input（reader）、config 全部落在
   `plugins/<name>/`。用户只需把一个目录放进 `plugins/`（内含 handler +
   profile），不改框架一行代码即可注册运行。
3. **全仓英文化**：除马来文文档、华文内容、DSKP/ERPH 两个词之外，所有马来文
   改为英文——含 YAML 键、CLI 旗标、日名值、标识符、报错、文档与测试。
4. **golden 字节不变（全程硬约束）**：所有改动只动"我方词汇与引用"，
   不动写入工作簿的内容。

## 已拍板的需求（对话定稿）

| # | 决定 |
|---|---|
| 1 | `inputs/yaml`（零业务的 profile loader）**留框架**（自举：框架必须先读 profile） |
| 2 | `Lesson/Schedule/Week/merge_periods` **搬进插件**；`model.py` 只剩 `Profile / ProfileInputs / HandlerSpec`（model 是核心层，不说业务） |
| 3 | **`assets/` 完全冻结**：不改、不改名、不移动任何一个东西；镜像边界原则生效（见下） |
| 4 | 插件发现 = **扫描 `./plugins/`（cwd）+ snake_case 目录约定式**，无清单文件 |
| 5 | `config/` **随插件走**；`assets/` **留原地** |
| 6 | 插件名 = **`erph`**（DSKP/ERPH 两个词不管，正好入名） |
| A/B/C | model 中立化；除马来文文档外马来文→英文（华文不管、DSKP/ERPH 不管）；`pyproject` description 与 README 的 e-RPH 定位文案**不动** |
| 1/2/3 | `inputs/calendar` 等业务 reader 算业务→进插件；字段名改英文；外部合同允许 breaking（尚无真实用户） |

### 马来文边界（镜像原则，需求 3 的落地口径）

- **我方词汇 → 英文**：键、标识符、旗标、报错、消息、文档、默认值。
- **必须与外部制品相等的 token 保留原样**（制品/官方名称的专有名词）：
  - 工作簿 sheet 名（`AHAD…KHAMIS`、`MENU`、`ISNIN`）与 `assets/` 下的一切
    （文件名如 `jadual-waktu-2026-siri-7.xlsx`、路径、文件内容）——**冻结**；
  - 源 timetable 表头（在插件镜像表中映射 `Ahad→Sunday`）；
  - 官方科目名（`BAHASA CINA`）与假日官方名称（`CUTI A.TAHUN 2026` 等
    数据内容值）——写进真实工作簿的内容，改了 golden 也会暴露；
  - profile 中指向真实 sheet 的参数值（`sheet: MENU`、`cells: [MENU, …]`）。
- ms-MY 文档：**散文不翻译**；其中的代码引用（路径/旗标/键名/示例）
  随各阶段机械同步（D5）。

## 插件契约（新机制）

```
plugins/erph/                     # snake_case 目录 = Python 包 erph
├── __init__.py
├── domain.py                     # Lesson/Schedule/Week/merge_periods + 日名镜像表
├── handlers/                     # 约定式注册：文件夹名 = handler 名
│   ├── __init__.py
│   ├── week/  menu/  fixed_cells/  dskp/        # 各含 DESIGN.md
├── inputs/                       # 约定式注册：文件夹名 = reader 名
│   ├── __init__.py
│   ├── calendar/  timetable/  dskp/             # 各含 DESIGN.md；dskp 有 __main__
├── profiles/
│   └── ali-bin-abu/profile.yaml  (+ DESIGN.md)
├── config/
│   ├── school-weeks/             # 原 config/jadual-minggu/
│   └── period-times/             # 原 config/period-times/
└── README.md                     # 业务索引（原 src/ranse/handlers/README.md 并入）
```

- **发现**：扫描 `./plugins/`（cwd；golden 子进程 cwd=仓库根天然命中）；
  目录名须为合法 snake_case 包名。约定式结构（含 `__init__.py` 层级），
  无清单文件；`handlers/<name>/`、`inputs/<name>/` 即注册。
- **引导**：新 `handlers/loader.py` 把 `./plugins` 插入 `sys.path` 后
  `import erph.handlers…`；测试 harness 自行做同样 bootstrap（`fn()` 直接 import）。
- **注册与错误 UX**（与静态注册表等价）：跨插件重名 = 加载即报错（列出两个来源）；
  profile 里 handler 名解析失败 → 报错并列出全部已发现名；
  找不到插件目录 → 中性提示（如 "no plugins found under ./plugins"）。
- **D2 反转**："静态内置注册表" → "**本地目录扫描发现**"——仍无 entry point、
  无安装元数据。`subcommands()` 机制保留，数据源改为插件扫描
  （出货 `erph` 无 SUBCOMMAND → `ranse --help` 继续只列 `{fill,write}`，
  既有帮助面守卫测试保持绿）。
- **打包**：wheel 只含 `src/ranse`（纯框架）；插件是本地目录、不进 wheel。
- **入口迁移**（已接受的 breaking）：`python -m ranse.inputs.dskp` →
  `python -m erph.inputs.dskp`。

## 阶段（每阶段：`pytest` 全绿 + golden 字节不变 + 单独提交）

### Phase 1 — Python 层英文化（不碰数据 schema、不碰日名值）

- CLI：`--minggu` → `--week`（`handlers/week` 的 `cli_options` dest 同步；
  `runtime` 键、README/ms-MY 旗标表、week DESIGN 同步）。
- 字段与占位符：`Week(minggu, siri)` → `Week(number, series)`；
  `Lesson.tingkatan` → `Lesson.form`；dskp 的 `{tingkatan}` 占位符 → `{form}`
  （regex、profile `file: "…t{form}.txt"` 同步——解析出的路径仍是
  `assets/bc-dskp/t1.txt`，**assets 不动**）；DESIGN §178 引用同步。
- 函数/变量/注释：`load_jadual_config`→`load_calendar_config`、
  `resolve_week(jadual_cfg,…)`→`resolve_week(calendar,…)`、
  `siri_to_timetable`→`series_to_timetable`、`jadual_*`→`calendar_*`、
  `per_minggu`→`series_by_week`、测试 fixture `def jadual()`→`def calendar_cfg()`、
  `JADUAL_YAML`→`CALENDAR_YAML`；散文里的马来日名/连接词全部英文化。
- 报错与报告句英文化：**此阶段仍引用旧数据键**（`'minggu'` 等，schema 未改），
  只改连接词与字段引用；如 "no dated 'minggu' records"。测试断言同步。
- `model.py`：仅改字段名与引用文档；类型整体搬迁在 Phase 3。
- 文档：week/dskp/menu/timetable/calendar DESIGN、README、ms-MY 代码引用。

### Phase 2 — 数据 schema 英文化 + 日名英文化（日名部分必须原子）

- 日历 schema 与文件：`config/jadual-minggu/` → `config/school-weeks/`、
  文件 `school-weeks.yaml`；键：`jadual:`→`timetable:`、`jadual_siri:`→`week_series:`、
  `minggu:`（记录表）→`weeks:`、记录键 `minggu`→`week`、`cuti`→`holiday`、
  `siri`→`series`；**假日名称值（官方名）不动**。
  报错文案改为引用新键（`has no 'weeks' records`、`no 'week' number`、
  `add inputs.calendar … or pass --week N`、`under 'timetable:'`…），测试同步。
- profile：`inputs.jadual` → `inputs.calendar`；路径
  `config/school-weeks/school-weeks.yaml`；`context.days: [Sunday…Thursday]`；
  注释英文化。`sheet: MENU/ISNIN`、`assets/…ERPH…` 路径、科目名**保留**。
- **日名英文化（同一提交，防 golden 漂移）**：
  1. timetable reader：源表头 `Ahad…Sabtu` → 规范英文日名
     （插件日镜像表 `_DAY_HEADERS`，xlsx + csv 两路）；
  2. `DEFAULT_DAYS` → 英文日名；
  3. menu/dskp 的 sheet 查找加反向镜像（`Sunday` → 模板实际 sheet 名）；
  4. `context.days` 过滤随 profile 同改 → **写入内容不变**。
- 测试 fixture：日名英文化、`CUTI` 键→`HOLIDAY`（值保留）、harness 断言同步。
- 文档：`config/school-weeks/DESIGN.md` 键表重写、profile DESIGN、
  README/ms-MY 的 profile 示例与 `inputs:` 键表。

### Phase 3 — `plugins/erph/` 重组

- `git mv` 搬迁（**assets 一个字节不碰**）：4 个 handler、3 个业务 reader、
  `config/` 两个数据目录、`profiles/ali-bin-abu/`；各 DESIGN.md 随文件夹走。
- 业务类型出 `model.py`：`Lesson/Schedule/Week/merge_periods` →
  `plugins/erph/domain.py`；`model.py` 只剩 `Profile/ProfileInputs/HandlerSpec`，
  docstring 中立化（e-RPH / Malay school days / `inputs.get("jadual")` 示例等全部清除）。
- `handlers/base.py`：`Context` 删除 `schedule / week / start_date` 三个类型化字段
  （改动态挂载，docstring 改为与 `requires`/`template_vars` 同款的不透明描述）；
  import 收缩为 `from ..model import Profile`。框架从此不再引用任何业务类型。
- 机制替换：静态 `handlers/registry.py` 与 `inputs._READERS` 名单 →
  `handlers/loader.py`（`sys.path` 引导 + 约定式扫描 + 合并注册 + 冲突报错）；
  `inputs.subcommands()` 数据源改扫描；`cli.py` 改 import（机械）。
- 相对 import 层级适配（`…inputs.calendar` → `..inputs.calendar` 等）；
  插件内 `domain` 共享（menu/dskp 的 `merge_periods`、timetable 的
  `Lesson/Schedule`、week 的 `Week`）。
- profile 路径引用：`inputs.calendar`/`period_times` 改为相对 profile 自身
  （`../../config/…`，经 `input_bases` 的 profile.base_dir 首位解析）；
  `template` 仍为 `assets/…`（cwd 回退解析，**assets 不动**）。
- 测试：harness `_PACKAGE_CANDIDATES` 增补 `erph.*` 并 bootstrap `plugins/`
  进 `sys.path`；业务测试 import 路径更新；根 `config/`、`profiles/` 目录消失。
- 文档：README/ms-MY 目录树与路径、`python -m erph.inputs.dskp`、
  `inputs/README`（框架侧只剩 profile loader + 指向插件）、
  `plugins/erph/README.md`（业务索引，含 config/ 内容并入）。

### Phase 4 — CI 与文档定稿

- `tests/test_architecture.py` 升级：
  1. **词表先 grep 定稿（零命中后写入断言）**：马来词全集
     （`jadual/minggu/cuti/siri/tingkatan/hari/waktu/sekolah/murid/guru/kelas/
     rancangan/pengajaran/harian/aktiviti/tarikh/…` + 七个马来日名）+
     框架可达的业务英语概念词（`week/schedule/lesson/subject/…`，以 grep 结果为准）；
     **DSKP/ERPH 不入词表**（需求：两词不管）。
  2. 扫描范围 = **整个 `src/ranse`**，`_VOCAB_EXEMPT` **清零**
     （注册表已死，框架内无任何业务点名）。
  3. 插件侧扫描：马来词表 + 镜像白名单 `_MIRROR_EXEMPT`（表头映射、
     sheet 映射常量，按文件+理由豁免，沿用现有模式）；DSKP/ERPH/MENU 不扫。
  4. 方向规则：框架（loader 除外）不 import 插件；`importlib`/`sys.path`
     仅限 loader 与测试 harness；插件只 import 框架与自身包内；插件互不 import；
     现有 core/cli/inputs 方向规则保留。
  5. 保留：`test_top_level_help_lists_only_framework_commands`（帮助面守卫）。
- `docs/DESIGN.md`：S2 重写（model = 中立配置结构；业务类型在插件）、
  §178 示例、D2 改写（本地目录扫描发现）、S3.3 键名、S3.4 旗标（`--week`）、
  S4、架构图与文件表、决策表（D2 机制变更 + D5 同步记录）。
- README + ms-MY：目录树（`plugins/erph/`）、快速上手、`--week`、
  "**写一个插件**"小节（约定式目录 = 全部注册动作，用户只碰 `plugins/`）；
  ms-MY 仅同步代码引用，散文不译。
- `PLAN.md` 状态头补记各阶段提交号。

## 风险与验证

- **golden 字节不变是每阶段硬约束**：Phase 1/3 纯改名与搬迁；Phase 2 日名
  翻译若漏一处 → 过滤错位 → golden diff 直接暴露（哨兵作用）。
  `BAHASA CINA`、假日名、`assets/` 冻结正是字节不变的前提。
- **日名翻译必须原子**（reader 映射 + `context.days` + sheet 镜像 +
  `DEFAULT_DAYS` 同一提交），否则半英半马错位。
- 报错文案变化需 grep 测试断言（老规矩）；golden 错误用例锁定
  "holiday week"（英文稳定段，键改名不影响）——每阶段复核。
- `sys.path` 引导：loader 与 harness 各自 bootstrap，避免同一包名经两个入口
  进 `sys.modules`；pip 安装（纯框架 wheel）+ 用户本地 `./plugins/` 形态可用。
- 每阶段收尾：`python -m pytest -q` 全绿 +
  `PYTHONPATH=src python -m ranse --help` 人工核对（Phase 4 起由 CI 断言）。
