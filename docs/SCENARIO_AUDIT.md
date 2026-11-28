# 扫描场景、负载事实审计与历史基准局限

状态：已依据 [ADR-0001～ADR-0021](decisions/README.md) 完成 Core 首版定型与减痛重构，并合并原历史基准局限说明；`A-01`（UMS 扫描流程）与 `A-03～A-07`/`A-12`（UMS 架构收敛输入）均已留档，本文仅作事实证据与审计入口，不新增规范或重跑旧实验。

总体架构见 [DESIGN.md](DESIGN.md)，唯一数据契约见 [DATA_SPEC.md](DATA_SPEC.md)，首版工程合同见 [SDK_CONTRACT.md](SDK_CONTRACT.md)，磁盘布局草案见 [WIRE_FORMAT.md](WIRE_FORMAT.md)，访问场景与验证计划见 [SPEC_TEST_PLAN.md](SPEC_TEST_PLAN.md)。

## 1. 审计范围与既定输入

本轮聚焦实际设备、采集序列、坐标/同步语义与算法消费事实的核对。Core 首版已在 [ADR-0016～0021](decisions/README.md) 完成定型与减痛：聚焦单晶与相控阵全波（`wave_and_feature`/`FeatureOnly`/`FMC` 归 M4）、中立容器 + 轻量 M:N `Region` + 逻辑拼接组 `ScanGroup` + 按 Scan 多次追加伴生快照与版本化旁路派生容器、大块解耦 `frames/meta` 与 `CellCoord` 排序索引、非 SWMR 只写一次 + 外部临时 `.wal` + 低频 `fsync` + 独立恢复子进程、单一 `stored_xxh3`、`none/shuffle+zstd/shuffle+lz4`、锁外并发 `pread` + 极简 `push`-only C11 ABI 静态单库及 `.NET`（`net10.0`/`net48`）首版绑定。若实际设备事实违反这些契约，记录范围冲突并回退 `DESIGN.md`/`DATA_SPEC.md`/`SDK_CONTRACT.md` 修订。

## 2. 先对齐四种“顺序”

| 对象 | 当前契约能力 | 审计核查缺口 |
|---|---|---|
| Frame 索引 `n` | Scan 内唯一记录身份与权威前缀，无效槽位以 LSB-first `valid=0`＋零填充表达 | 上游位图来源、各模式帧结构与最大帧字节规模（`D-02`） |
| 设备来源 trigger/event ID | 可选列式 `required`/`nullable` 附加记录，由上游适配层先消化硬件回绕 | 跳号/重复语义、多事件来源说明 |
| 原始采集位置 | Frame 绑定历史位置，PA 同帧共用 `P_n`，带显式 `pos_valid` 与同步等级 | 参考系、单位与实际同步等级覆盖 |
| 空间网格/算法顺序 | 可选定长整型 `CellCoord[Frame]`（含无归属标记）+ `complete_scan()` 不可变排序索引实现百 GB `O(log N)` 查回；3D 索引归 M4 扩展层 | 往返/蛇形扫描线与五类访问实际权重（`D-03`） |

位置值相等不合并 Frame，帧相邻不证明空间邻接，共同 Frame 不证明同时激发；采集层保证原始绑定准确性，SDK 不做时间配准。

## 3. 扫描场景核查

| 主题 | 当前契约入口 | 进入 M2 薄切片前需补充的真实设备/业务事实 | 影响边界 |
|---|---|---|---|
| A-01 一次扫描的边界 | [SCAN-01/02](DATA_SPEC.md#scan-01)、[LIF-01](DATA_SPEC.md#lif-01)：中立容器、轻量 M:N `Region`、`ScanGroup`、`EndStatus`、`cancel_empty_scan`、关闭 `D-15` | UMS 流程已记录见 [ums-scan-flow](#ums-scan-flow)；外部写入方多区域拼接与复检需求 | D-11 / D-19 |
| A-02 轨迹与触发方式 | [REC-01](DATA_SPEC.md#rec-01)、[POS-02](DATA_SPEC.md#pos-02)：记录轴非空间网格，大块 `frames/meta` + `CellCoord` 排序索引 | 非等距触发、往返/蛇形扫描方向、编码器来源与步进-触发时序 | D-02 / D-03 |
| A-03 输出与物理测点 | [WAV-01](DATA_SPEC.md#wav-01)、[REL-01](DATA_SPEC.md#rel-01)：单晶/PA 独立 Schema、清晰区分阵元与合成输出 | 首批单晶/PA 设备真实事件—接收输出—通道/声束映射与最大 Frame 字节数 | D-02 / D-09 |
| A-04 位置及异常 | [POS-01/02](DATA_SPEC.md#pos-01)：无位置合法、`pos_valid=0` 保全有效波形、编码器逐轴有效掩码、姿态约定、`crs_transforms` | 首批设备具体位置结构体与 `nullable` 附加记录清单 | D-01 / D-09 |
| A-05 已有数据解释 | [REL-01](DATA_SPEC.md#rel-01)、[META-01](DATA_SPEC.md#meta-01)：C11 强类型最小解码核 + ASTM E2339/E2663 可选物理表（水浸/多探头/2D-TCG/PCS）+ 参数化曲面几何 + `VendorExtension` | 单晶/PA 首批设备字段清单与单位核对 | D-09 |
| A-06 存储阻塞与中断 | [MAP-02](DATA_SPEC.md#map-02)、[WRT-01/03](DATA_SPEC.md#wrt-01)、[LIF-02](DATA_SPEC.md#lif-02)：非 SWMR + 外部临时 `.wal`、低频 `fsync`、独立子进程隔离恢复、禁重试 | 调用方 Flush 频率、可接受损失窗口与退场超时参数 | D-02 / D-05 |

<a id="ums-scan-flow"></a>
### UMS 扫描流程记录（A-01）

| 模板项 | UMS 输入（已依据 ADR-0016～0018 对齐） |
|---|---|
| 场景 | UMS 一次执行（Run）按段日程顺序扫描工件上的多个区域 |
| 证据来源 | UMS 设计文档（段与段日程、存储规格），用户于 2026-11-19/20 确认并在 2026-11-27 由 `ADR-0016～0018` 裁决闭合；属设计阶段业务输入 |
| 实际动作与预期结果 | Start 创建 Run 并冻结段日程（每区域一段、顺序执行、段间转场；标定采用值冻结，当前仅扫描速度逐区域变化）。暂停后继续仍属同一段（同一 `Scan`）；Stop 或故障使当前段提前结束并记录 `EndStatus` 与未执行区域（空 `Region`）；若尚无任何已提交帧即中止则直接放弃删除不产出空文件；收尾封存，成果以文件为准，可重建目录 |
| 复检与跨进程 | 复检为另一次独立 Run，数据位于另一份已封存文件；跨文件复检关系整体归 `D-19`（定案前由 UMS 持有）；跨进程断点续扫已后置，不需要干净关闭后重开追加（`D-15` 已关闭） |
| 容器与实体映射（已定） | 一次 Run 写一份独立中立容器文件；文件中包含轻量 M:N `Region` 实体，每执行段对应一个引用 `RegionID` 的 `Scan`；段内暂停留在同一 `Scan` 内；Run 到 Scan 映射留在 UMS 调用方 |
| 审计主题与规则 | A-01、A-09；`R-01`/`R-12`；`SCAN-01/02`、`RET-01`、`LIF-01`；`D-11`（M2 精确字段名）、`D-19`（跨文件复检） |
| 结论与最小验例 | 契约方向已闭合。最小验例：三段文件，段二暂停后继续、段三 Stop 提前结束，重开枚举三 Scan、段二帧序连续、段三显式标示提前结束并保留未执行空 Region（`UC-19`/`20`） |

<a id="ums-arch-inputs"></a>
### UMS 架构收敛补充输入（2026-11-27：A-03～A-07、A-12）

记录 UMS 本轮架构收敛中与独立存储 SDK 衔接的既定边界与上游工程事实：

1. **原始整数码分叉与 `SignalDescriptor`（A-03 / A-07 → D-02 / D-09）**：UMS 在 `Ingress Decode` 之前分叉落盘，提交紧凑硬件原始位宽码（如 PA 8/16-bit、X1078 原码），离线复用同一 `Ingress Decode`；固定定义须携带完整 `SignalDescriptor`（有效 ADC 位、对齐、端序、零点/比例及 `RawRF / Rectified / AnalyticEnvelope / LogDb` 标签）以保留 ADC 顶格饱和证据。
2. **参数分层与厂商扩展（A-05 → D-09）**：UMS 参数收口为“最小解码核 + DICONDE/NeXus 强类型可选物理表 + `VendorExtension`”，单次 Scan 内参数结构冻结；以 ASTM DICONDE（**E2339 / E2663**；原笔记所记 E2738 为计算机射线 CR 标准，已于 [ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md) 纠偏）与 NeXus 作字段完备性核对清单（不采用 DICOM 二进制编码）。
3. **帧号回绕消化与位置同步等级（A-02 / A-04 → D-01 / REC-01）**：UMS 采集适配层内部消化硬件 8/16-bit 回绕并提交单调帧序；位置元数据显式标注同步可靠性等级（`HardwareSynchronized` / `StepAndShootVerified` / `SoftwareTimestampPaired` / `Unavailable`）。
4. **Scan 特征结构冻结与硬件直出特征（A-01 / A-03 → RET-01 / D-16）**：在线扫描期间冻结输出特征结构（仅允许调整已启用闸门数值参数，增删闸门须停机重准）；“仅特征 + 硬件直出特征”走预留的独立不可变 Schema，封存后不可被离线重算覆盖。
5. **三档异常退场、`EndStatus` 与 `LIF-02` 联动（A-06 → RET-01 / LIF-01 / LIF-02 / D-05）**：外设故障进程健康时保留重试/另存/显式放弃；主干崩溃退场执行有界超时尽力封存（仅特征不临时转全波），超时或失败后留痕退出，下次启动交存储适配层按 `LIF-02` 显式原地只读核验；`Scan` 显式记录正常/主动提前/故障结束状态并配合空 `Region` 表达缺口。
6. **上位机内存池与职责排除（A-12 → `SDK_CONTRACT.md` / BUS-01）**：UMS 数据面采用预分配 `Batch-of-SoA` 批租约池＋离线分块重算，与 SDK 的 `push` 两阶段读 + 块几何/容量查询 + `.NET` 非托管 >2 GiB 缓冲契合。UMS 自包含目录索引、崩溃 `Tombstone`、激光点云与 DDG 网格、在线分发租约池、标注/缺陷成果与外部科研录放均明确留在 UMS 侧，不进入 SDK。

## 4. 算法输入与读取方式核查

| 主题 | 审计问题 | 契约关联 |
|---|---|---|
| A-07 波形数值与采样轴 | 原始整数码与 `f32` 按位保真、`SignalDescriptor` 与传播距离模型依赖 | [WAV-01/02](DATA_SPEC.md#wav-01)、`D-02`/`D-09` |
| A-08 单 Frame 内选择 | 帧内流/声束/样本选择边界，整体拒绝与内存连续性要求 | [READ-02](DATA_SPEC.md#read-02)、`SDK_CONTRACT.md` |
| A-09 空间显示与重建 | 文件内轻量 M:N `Region`、跨文件复检（`D-19`）与外部坐标重建边界 | [SCAN-02](DATA_SPEC.md#scan-02)、[POS-02](DATA_SPEC.md#pos-02) |
| A-10 Batch 与算法消费 | 连续 `push` 读（离散清单 v0.2）、每组独立缓冲、`staging_budget`、锁外并发 `pread` 与 GPU 双缓冲 `push` | [READ-03](DATA_SPEC.md#read-03)、[BUF-01](DATA_SPEC.md#buf-01)、`SDK_CONTRACT.md` |
| A-11 有效性与可复现性 | LSB-first packed bitset 区分有效全 0 与零填充、四种内容状态与来源追溯 | [STA-01](DATA_SPEC.md#sta-01)、[RET-01](DATA_SPEC.md#ret-01)、[PAR-01](DATA_SPEC.md#par-01) |
| A-12 执行与资源 | 在线走采集内存 vs 离线走封存文件；全链路峰值内存与吞吐门槛 | [CAP-01](DATA_SPEC.md#cap-01)、[CMP-02](DATA_SPEC.md#cmp-02)、`D-02`/`D-03`/`D-06` |

### 每个真实工作负载应留下的最小记录

对每个实际消费或写入工作负载记录：**输入来源与阶段**（采集内存/封存文件/`LIF-02`）、**选择与顺序**、**解释依赖**（采样轴/`SignalDescriptor`/几何）、**输出与所有权**（`poll`/`push`、单 Frame 不分块）、**全链路峰值内存与负载指标**（区分调用者缓冲、SDK 暂存、HDF5 缓存与 `.NET` 绑定副本），以及**独立期望样例**（未知项显式留空）。

## 5. 设计细节核对与归位分类

审计中新增必需信息时，按四类职责归位（不提前绑定 HDF5 路径）：

- **固定定义与解释**：最小解码必填核（`SignalDescriptor`/采样轴/映射）、DICONDE/NeXus 可选物理表、参数化曲面几何与 `VendorExtension`（`PAR-01` / `META-01` / `REL-01`）。
- **Frame 观测与列式附加记录**：原始波形/LSB-first 位图、帧位置/`pos_valid`/同步等级、可选 `CellCoord` 与 `required`/`nullable` 附加记录（`POS-01/02` / `STA-01`）。
- **中立容器、Region 与 Scan 状态**：容器角色、`FileInstanceUUID`、轻量 M:N `Region` 实体、`Scan` 身份与 `EndStatus`、可选工件/Run 元数据（`ID-01` / `SCAN-01/02`）。
- **伴生/旁路快照与外围分工**：采集期伴生 C 扫快照写主文件（封存前 Write-Once）；离线派生写 Write-Once 旁路容器（`SNAP-01`）；3D 空间索引与多回波选择（`D-17`）、窗口选峰（`D-18`）归 M4 扩展层；标注/缺陷与点云留 UMS。

## 6. 审计记录与收敛方法

```text
场景/算法名称：
证据来源与适用设备/版本：
实际动作、输入与预期输出：
对应审计主题 A-xx：
涉及需求 R-xx / Spec 规则 / 待定项 D-xx：
结论：现有契约覆盖 / 需要补充 / 与现有约束冲突 / 本轮不适用 / 证据不足
拟调整内容及理由（未决定时明确标注）：
最小验证样例与独立期望值：
```

结论严格按 [ADR-0007](decisions/0007-documentation-structure.md) 归位：已覆盖直接引用规则号；新待定仅在证据充足时补充至 `DATA_SPEC.md`；冲突先修订 `DESIGN.md`、`DATA_SPEC.md` 与 `SDK_CONTRACT.md`，严禁在实现或测试中偷加例外。

---

<a id="historical-benchmark-limits"></a>
## 7. 历史微基准证据局限与后续性能取证条件（合并自原 BENCHMARK_REPORT）

> **状态：历史探索，不是生产性能基线、格式符合性证据或当前选型结论。**（归档脚本见 [archive/benchmarks/ultrasound_storage_baseline/](../archive/benchmarks/ultrasound_storage_baseline/README.md)；移除的旧六布局脚本与精简前报告可从 Git 提交 `8acf776` 查阅。）

| 历史实验局限 | 不能据此得出的结论 |
|---|---|
| 输入是合成 RF，参数范围有限，没有真实设备持续输入 | 产品压缩率、实际吞吐、设备端不丢数据 |
| 完整回读预热、OS 缓存未受控，SPLIT/CTS 活跃通道可用缓存不同 | 冷盘带宽、纯解压速度或布局的普遍优劣 |
| 扩展实验同时改变数据量、chunk、缓存、批量及部分 codec；采样和原始计时不足 | 单因素因果、稳定尾延迟或生产默认值 |
| 部分历史汇总与现存结果不一致；缺少完整脚本/运行库/存储环境绑定 | 严格可复现的性能基线 |
| 写入含重排、resize、flush、close，没有进程崩溃取证 | Flush 后条件（WRT-03）或确定恢复窗口 |
| 缺完整位置、固定定义（PAR-01）、封存/恢复契约及等价的逐请求校验 | 生产 SDK 能力或 Spec 符合性 |
| 源数据全量驻留内存，没有从实际 filter 表示完成 GPU 解压 | 超 RAM 单文件验证或 GPU 解压能力 |

**M3 性能取证前置条件**：补齐真实设备输入速率、访问权重与全链路内存预算（`D-02`/`D-03`）后，基于正式 C++20 引擎执行控制变量实验：① `none` vs `shuffle+zstd` vs `shuffle+lz4`；② 真实波形与不可压缩压力输入对照；③ 明确冷/热缓存状态、完整环境与原始计时；④ 超 100 GB 超 RAM 块对齐 `push` 流式读写与 M4 可选 GPU `nvCOMP` 端到端对比。
