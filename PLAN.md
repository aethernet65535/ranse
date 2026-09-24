# PLAN — Core/CLI/Inputs 去业务化（框架与业务解耦）

审计结论：框架层（`core/`、`cli.py`、`inputs/yaml/`）存在 DSKP/ERPH 业务残留——
硬编码的业务 key、领域词汇直接进入编排器、业务 loader 放在通用目录、
day 过滤与节次时间表写死在代码里、`_REPO_ROOT` 路径回退对 pip 安装不安全。
本计划把**机制留给框架，词汇与策略留给业务**，同时保持外部使用体验不变。

## 边界认定

1. **"词汇中立"指框架代码不再说业务话**：`cli.py`、`inputs/yaml/`、`inputs/calendar/`、
   `core/`、`model.py` 的框架面不再出现 `minggu/jadual/MENU/DSKP/…`；
   示例业务自己的配置（profile 的 `inputs.jadual`、`--minggu` 旗标、
   `Ahad/Khamis` 日名、日历文件的 `minggu/cuti/siri` 键）是业务数据与业务 UX，**保留**。
2. **ProfileInputs 的 breaking 是 Python 层的**：删除 `jadual/timetable/csv` 硬编码字段，
   改为通用 `inputs` 透传 + `inputs.get(key)`；profile YAML 的 key 不改名（对外零破坏）。
   profile 仍需同步修改：新增 `context.days` 与 `inputs.period_times`（Phase 4）。

## 阶段（每阶段结束跑 `pytest` 保持绿）

### Phase 1 — core 小清理
- `core/xlsx.py` docstring 示例 `"MENU!B3"` → `"SHEET!B3"`（去业务词汇）。
- 新增 `core/format.py`：从 `xlsx.py` 拆出格式层原语（`NS/NS_R`、`read_zip`、
  `parse_sheet_rels`、`parse_sheet_names`、`read_shared_strings`，改为公开名）——
  这是 inputs 读源文件时借用的部分；`xlsx.py` 只留 write-only 的 `Workbook/Sheet`。
- `inputs/timetable/__init__.py` 改从 `core.format` 导入（不再摸 core 私有面）。
- `tests/harness.py` `_PACKAGE_CANDIDATES` 增加 `ranse.core.format`、`ranse.inputs.calendar`。

### Phase 2 — Profile 模型/loader 通用化 + 日历 loader 搬家
- `model.py ProfileInputs`：删 `jadual/timetable/csv` 字段 → `extra: Dict[str, str]`
  透传 + `get(key, default)`；docstring 更新。
- `inputs/yaml/__init__.py`：`load_profile` 不再点名业务 key；框架只特判
  `template`（必填）/`templates`（周号映射），其余 key 走通用形状校验
  （非空字符串或 mapping），语义校验交给消费者（与"各 handler 校验自己的 params"对称）；
  `resolve_template` 报错去掉 `set inputs.jadual` 字样，改中性表述。
- 新增 `inputs/calendar/__init__.py` + `DESIGN.md`：`load_jadual_config` 从
  `inputs/yaml/` 搬来（README 规定"一个格式一个文件夹"）；`sys.exit(1)` 改
  `raise ProfileError`（错误路径统一走 D13）。
- `handlers/week`：`inputs.jadual/timetable/csv` → `inputs.get(...)`；
  `load_jadual_config` 改从 `inputs.calendar` 导入。
- `tests/test_profile.py`：字段访问与 `resolve_template` 调用点适配。

### Phase 3 — CLI 词汇中立 + 声明式扩展点
- `handlers/base.py Context`：新增 `template_vars: dict`（`inputs.template` 的
  `{…}` 占位符取值来源）；`needs_schedule` 声明改为 `requires = ("schedule",)`
  （业务声明的不透明名字，框架只做存在性检查）；docstring 同步。
- `handlers/week` resolve 发布 `ctx.template_vars["week"]`——词汇转换只发生在业务内。
- `cli.py`：`resolve_template(profile, ctx.template_vars)`（`_run_fill`/`_run_write`）；
  `_require_something_to_do` 泛化为"每个 filler 声明的 `requires` 是否都能满足，
  全部受阻才报错"（语义逐条保持：dskp 无 requires → 放行）。
- `inputs/__init__.py`：去掉 `from . import dskp`，改惰性注册表
  `_READERS = ("dskp",)` + `subcommands()`（`importlib` 收集 `SUBCOMMAND`）——
  新业务只改这一行，`ranse fill` 启动不再加载 dskp reader（符合 D2 精神）。
- `cli.py` `_SUBCOMMANDS` 改在 `_build_parser` 内构建。
- `errors.py`：删死代码 `WeekError`（全仓库无人 raise）；`docs/DESIGN.md` S6 同步。
- `handlers/menu`：`needs_schedule = True` → `requires = ("schedule",)`。

### Phase 4 — 业务数据归位
- **day 过滤从 reader 移到业务**：`inputs/timetable` 不再丢 Jumaat/Sabtu（消除对
  D8 的张力）；profile 新增 `context: {days: [Ahad, Isnin, Selasa, Rabu, Khamis]}`，
  menu 与 dskp 两个 filler 共读（risk 3：共享值放 `context:`）；handler 内保留
  缺省值 = 现行为。
- **`PERIOD_TIMES` 数据化**：新增 `config/period-times/period-times.yaml`
  （period → [start, end]），profile 经 `inputs.period_times` 引用（可选，缺省
  回落内置表 = 现行为）；`TIME_PERIOD` 反向表由正表派生，消除双份硬编码（D11 落地）。
- `config/` 加目录与 DESIGN；`inputs/timetable/DESIGN.md`、menu/dskp handler DESIGN 更新。

### Phase 5 — `_REPO_ROOT` 路径回退
- 回退仅在源码检出时生效（`_REPO_ROOT` 下存在 `pyproject.toml` + `src/ranse` 才启用）；
  pip 安装后 bases = `[profile.base_dir, cwd]`。
- 统一三处各自拼的 base 列表（`inputs/yaml._input_bases`、`handlers/week`、
  `handlers/dskp`）到一个导出函数。

### Phase 6 — 防回归 + 文档
- 新增 `tests/test_architecture.py`：
  1. AST 导入方向检查：`core/**` 不 import `ranse.handlers`/`ranse.inputs`；
     `cli.py`/`inputs/yaml`/`inputs/calendar` 不 import 具体业务 reader 与 `handlers.*`；
  2. 业务词表扫描：框架文件禁出现
     `DSKP|ERPH|MENU|jadual|tingkatan|minggu|cuti|siri|Ahad|…`
     （注册表文件作为"业务接入点"白名单豁免，注释说明）——D6 从文档变成 CI 断言。
- 文档：`docs/DESIGN.md`（S2 文件表、S3.2 `requires`、S3.3 inputs schema、S6 删
  WeekError）、`README.md` 与 `docs/translations/ms-MY/README.md` 同步（D5）、
  `inputs/README.md`、`inputs/yaml/DESIGN.md`、新 `inputs/calendar/DESIGN.md`、
  `handlers/README.md`、`handlers/week|menu|dskp` DESIGN、
  `profiles/ali-bin-abu/{profile.yaml,DESIGN.md}`。

## 风险与验证

- **黄金回归必须字节不变**：全部为等价重构，days/period_times 都有保留现行为的缺省；
  `pytest`（本机有 `assets/`）会跑 golden 对比——sheet XML 漂移即等价性被破坏。
- 错误文案变化（"nothing to do…"、`{week}` 缺失提示）不影响 golden 错误用例
  （只断言 "holiday week"），需 grep 测试确认无断言旧文案。
- 严格按 Phase 1→6 执行，每阶段单独提交，方便定位回归。
