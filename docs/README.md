# 文档索引

[返回项目入口](../README.md)。状态：已依据 [ADR-0001～ADR-0021](decisions/README.md) 完成 Core 首版定型与架构减痛重构（Spec `0.3-draft` + [WIRE_FORMAT.md](WIRE_FORMAT.md) `1.0-draft r2`），准备停止文档扩张并转入极简 `uss.h` 与代码驱动的 Linux/Windows 薄垂直切片实现。

## 文档导航与唯一职责

按 [设计维护原则](DESIGN.md#integration-policy) 与 [ADR-0007](decisions/0007-documentation-structure.md) 分工：每份文档承担单一职责，不重复维护第二套规则。

### 核心设计文档（必读）

| 顺序 | 文档 | 唯一职责 |
|---|---|---|
| 1 | [DESIGN.md](DESIGN.md) | 两层架构全景、核心架构决定总览、需求基线（`R-01`–`R-20`）与首版排除范围 |
| 2 | [DATA_SPEC.md](DATA_SPEC.md) | 唯一权威**数据与存储契约**：逻辑模型、分模式 Schema、`ScanGroup`/复检、非 SWMR+外部 `.wal` 耐久与子进程恢复、不变量（`U-01`–`U-16`）与 `D-01`–`D-19` 状态总表 |
| 3 | [SDK_CONTRACT.md](SDK_CONTRACT.md) | **Core 首版工程合同**：首版交付矩阵、编码 Profile、极简 `push`-only C11 ABI 与状态机、`staging_budget`、哨兵锁与跨平台加固、`.NET`（`net10.0`/`net48`）绑定与版本门禁 |
| 4 | [WIRE_FORMAT.md](WIRE_FORMAT.md) | **M2 HDF5 Wire Format 1.0 草案（`1.0-draft r2`）**：容器头/能力位、双槽 `/lifecycle`、`Region`/`ScanGroup`、SingleProbe/PhasedArray 必填核与 E2663 可选物理表、大块 `frames/meta` + `cell_index`、外部 `.wal`、多 Scan/按层快照与版本化旁路 |
| 5 | [DECISION_DIRECTIONS.md](DECISION_DIRECTIONS.md) | 仅列剩余待补实机事实输入、M2 薄切片任务与 v0.2/M4 后置项 |
| 决策记录 | [decisions/](decisions/README.md) | `ADR-0001`–`0021`（一页一事），完整记录各项已采纳决定的背景、理由、证据与后果 |

### 验证与事实审计文档（按需查阅）

| 文档 | 唯一职责 |
|---|---|
| [SPEC_TEST_PLAN.md](SPEC_TEST_PLAN.md) | 访问场景映射与 TFM 边界、`H/P/F/W` 独立数值期望、`UC-01`–`UC-27` 与 `T-01`–`T-24` 验证规划、M0–M4 里程碑与 Core M3 验收门禁 |
| [SCENARIO_AUDIT.md](SCENARIO_AUDIT.md) | UMS 扫描流程与架构输入留档、设备/算法审计清单与历史微基准证据局限 |

## 契约章节快速入口

- **数据与存储契约（`DATA_SPEC.md`）**：
  - 产品与两层边界：[DOC-01](DATA_SPEC.md#doc-01)、[CORE-01](DATA_SPEC.md#core-01)、[API-01](DATA_SPEC.md#api-01)、[BUS-01](DATA_SPEC.md#bus-01)、[RET-01](DATA_SPEC.md#ret-01)、[REL-01](DATA_SPEC.md#rel-01)、[SNAP-01](DATA_SPEC.md#snap-01)、[ACCESS-01](DATA_SPEC.md#access-01)、[MEAS-01](DATA_SPEC.md#meas-01)
  - 容器、身份与模式数据：[逻辑模型](DATA_SPEC.md#logical-model)、[SCAN-01/02](DATA_SPEC.md#scan-01)、[REC-01/02](DATA_SPEC.md#rec-01)、[ID-01/02](DATA_SPEC.md#id-01)、[META-01](DATA_SPEC.md#meta-01)、[WAV-01/02](DATA_SPEC.md#wav-01)、[STA-01](DATA_SPEC.md#sta-01)、[POS-01/02](DATA_SPEC.md#pos-01)、[PA-01](DATA_SPEC.md#pa-01)、[PAR-01](DATA_SPEC.md#par-01)、[FMC-01/02](DATA_SPEC.md#fmc-01)
  - 物理引擎、耐久、读取与追踪：[MAP-01/02](DATA_SPEC.md#map-01)、[WRT-01–03](DATA_SPEC.md#wrt-01)、[IO-01](DATA_SPEC.md#io-01)、[LIF-01/02](DATA_SPEC.md#lif-01)、[READ-01–03](DATA_SPEC.md#read-01)、[BUF-01](DATA_SPEC.md#buf-01)、[CAP-01](DATA_SPEC.md#cap-01)、[CMP-01/02](DATA_SPEC.md#cmp-01)、[VAL-01](DATA_SPEC.md#val-01)、[不变量 U-01–U-16](DATA_SPEC.md#invariants)、[待定项 D-01–D-19](DATA_SPEC.md#open-items)
- **工程合同与交付规格（`SDK_CONTRACT.md`）**：[交付矩阵](SDK_CONTRACT.md#scope-matrix) · [编码 Profile](SDK_CONTRACT.md#encoding-profile) · [C11 ABI 与状态机](SDK_CONTRACT.md#c-abi-lifecycle) · [极简 `push` 与暂存预算](SDK_CONTRACT.md#core-io-batch) · [C++20 加固与 `.NET` 绑定](SDK_CONTRACT.md#platform-bindings) · [版本与 `1.0` 门禁](SDK_CONTRACT.md#versioning)
- **M2 Wire Format 1.0 r2（`WIRE_FORMAT.md`）**：[HDF5 加固](WIRE_FORMAT.md#hdf5-profile) · [容器头与能力位](WIRE_FORMAT.md#container-header) · [层次结构](WIRE_FORMAT.md#hierarchy) · [双槽 `/lifecycle`](WIRE_FORMAT.md#lifecycle-and-meta) · [`Region` 与 `ScanGroup`](WIRE_FORMAT.md#regions) · [分模式 Schema](WIRE_FORMAT.md#scan-schemas) · [波形与编解码](WIRE_FORMAT.md#waveforms-and-codecs) · [大块帧元与 `cell_index`](WIRE_FORMAT.md#frame-columns) · [外部 `.wal` 与提交](WIRE_FORMAT.md#map02-wire) · [多 Scan 快照与版本化旁路](WIRE_FORMAT.md#snapshots-wire) · [锁外并发与子进程恢复](WIRE_FORMAT.md#recovery-and-verify) · [H/P 样例](WIRE_FORMAT.md#worked-examples)

历史参考与实验入口：[归档说明](../archive/README.md) · [M1 实验说明](../experiments/m1/README.md)。
