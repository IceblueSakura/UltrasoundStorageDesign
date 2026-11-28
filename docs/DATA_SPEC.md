# 超声采集数据 Spec 0.3-draft

状态：`0.3-draft`，已依据 [ADR-0001～ADR-0021](decisions/README.md) 完成 Core 首版设计与架构减痛重构（[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）；本文是数据语义、物理存储架构、不变量与 `D-01`–`D-19` 状态的唯一规范来源。公开极简 C11 ABI、编码 Profile、锁与跨平台加固、`.NET` 绑定与版本门禁见 [SDK_CONTRACT.md](SDK_CONTRACT.md)，二进制磁盘布局草案见 [WIRE_FORMAT.md](WIRE_FORMAT.md)；不修改或重跑既往实验与 benchmark。

总体架构与需求理由见 [DESIGN.md](DESIGN.md)，访问场景与验证计划见 [SPEC_TEST_PLAN.md](SPEC_TEST_PLAN.md)，场景与负载事实见 [SCENARIO_AUDIT.md](SCENARIO_AUDIT.md)，剩余未闭项与 M2 待补输入见 [DECISION_DIRECTIONS.md](DECISION_DIRECTIONS.md)。

## 1. 规范状态、两层边界与核心契约

<a id="doc-01"></a>
### DOC-01：规范状态与声明边界〔确定〕

| 标记 | 含义 |
|---|---|
| 〔确定〕 | 已确认需求及在当前架构下的必要契约；“必须/不得”具有约束意义 |
| 〔参考〕 | 用于样例和实现探索的候选映射/行为；选择采用时按该规则验证，但不等于产品格式已冻结 |
| 〔待定〕 | 尚无正式决定；实现或测试不得把临时值描述为本 Spec 的规定 |
| 〔已替代〕 | 保留历史编号供追踪，不作为活动契约或通过证据 |

- **两层模型与首版聚焦**：本规范确立 **SDK Core + 独立可选扩展层**两层架构（[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)）。Core 首版（M2 薄切片 / M3 交付）聚焦 **单晶（`SingleProbe`）+ 相控阵（`PhasedArray`）全波（`full_wave`）+ 伴生/旁路 C 扫快照**；仅特征采集（`FeatureOnly`）、逐帧流式硬件特征（`wave_and_feature`）与 `FMC` 均在枚举中保留预留口，归 M4 统一展开（[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）；独立可选扩展层仅消费 Core 只读 API，不进入 Core 文件格式与写入路径。
- **格式兼容性与自描述分工**：底层使用 HDF5 2.x 库（非 SWMR）写出 HDF5 1.10–1.14 兼容格式（[ADR-0005](decisions/0005-file-format-range.md)），取消 HDF5 1.14 独立读取器双实现强制门禁（全员通过静态自包含单库访问，[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）。自描述指“仅凭文件与 SDK 即可完整解释并按触发号、空间坐标、声束号等参数访问，不依赖 UMS 或业务数据库”；不再承诺外部工具（如 `h5py`）不经 SDK 裸翻内部路径。
- **版本与历史证据边界**：`0.3-draft` 为文档状态标签，以 Git 提交区分修订；文件格式版本、模式 Schema 版本与 SDK SemVer 彻底解耦，`0.x` 允许演进，`1.0-rc`/`1.0.0` 起冻结（[ADR-0020](decisions/0020-implementation-stack-bindings-and-versioning.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）。`experiments/m1/` 为 test-only 机制原型，仅用于 M1 原适用范围取证，不能替代产品验收。

<a id="core-01"></a>
### CORE-01：两层架构边界与极简 `push`-only Core I/O〔确定〕

- **Core 与扩展层职责**：Core 负责中立交付容器外壳、分扫描类型独立 Schema、Write-Once 封存只读（含 `FileOpen` 态按 Scan 多次追加不可变伴生快照）及 Write-Once 版本化旁路派生容器、按触发连续区间 `push` 读与 `CellCoord` 排序索引 `O(log N)` 寻址，以及共享物理 I/O 引擎；选峰基础取值（[MEAS-01](#meas-01)）与 3D 旁路空间索引/多回波代表选择（[ACCESS-01](#access-01)）归 M4 独立可选扩展层。
- **极简 `push`-only Core I/O（[ADR-0006](decisions/0006-core-io-and-selection-layer.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）**：原始波形路径提供同步单 Frame 与 Frame 批次写入。Core C11 读取收敛为单一连续区间 `push` 原语（取消 `poll` 借用状态机与 C ABI 内纯内存帧内选择层，合并分析与 Batch 读取，离散帧清单留至 v0.2 增量追加）；按一个 Scan、连续帧区间 `(start, count)`（`count >= 1`）及一个或多个流组交付每组独立稠密样本、有效性位图及可选帧元/位置缓冲，不跨 Scan 自动拼接。帧内流/声束/Tx/Rx/样本花式索引由调用方在稠密内存或可选上层辅助库完成。
- **并发与锁边界（[ADR-0004](decisions/0004-concurrency-and-borrow-scope.md)、[ADR-0009](decisions/0009-review-contract-clarifications.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）**：进程内 HDF5 元数据调用经全局互斥锁串行化，**只读物理块 I/O、校验与解压移出全局锁**（锁内微秒级查块偏移，锁外经独立只读 OS 句柄并发 `pread`/`ReadFile`，保障多 Reader / GPU 双缓冲扩展且不阻塞 `.NET` GC Finalizer）。同一 Reader 或 Writer 对象不得并发调用；同一文件同一时刻仅允许一个 Writer，写入期间通过 OS 文件唯一 ID 注册表 + 常驻哨兵字节锁（`F_OFD_SETLK`/`LockFileEx`）主动拒绝同/跨进程 Reader（不依赖可被环境变量禁用的 HDF5 文件锁）。已封存文件可多进程同时只读。

Core 不负责设备协议解码、帧号回绕展开、时间配准、位置插值或业务字节序转换；平台、实现语言与绑定范围见 [SDK_CONTRACT.md](SDK_CONTRACT.md)。

<a id="api-01"></a>
### API-01：公开接口的稳定边界〔原则与策略已定，极简 `uss.h` 紧接落地〕

原生库唯一稳定边界为 **极简 `push`-only 纯 C11 ABI**（不透明句柄、64 位长度、指针＋字节长显式缓冲、`struct_size` 可扩展参数、未识别 `flags` 报错、稳定错误码与 `COMMITTED / NOT_COMMITTED / UNKNOWN` 提交状态分离；最小解码必填核走强类型 C11 结构体，可选物理表与 `VendorExtension` 走带机读 JSON Schema 的 UTF-8 JSON），不泄漏 HDF5 或 C++ 类型/异常（[ADR-0010](decisions/0010-public-api-stability.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）。详见 [SDK_CONTRACT.md](SDK_CONTRACT.md)。

<a id="bus-01"></a>
### BUS-01：超声专用产品边界〔确定〕

SDK 是包含权威 schema 与规范读写能力的单一超声数据存储产品，独立维护并开源：

- **三类使用者与跨系统交付（[ADR-0015](decisions/0015-cross-system-data-delivery.md)）**：面向 **UMS 保存与重开**、**其他扫描系统创建扫描数据**、**其他系统集成与外部分析完整读取**；读写合同与调用方的 Run、工件、Workflow 或业务数据库解耦（工件与 Run 为可选元数据）。仅凭文件与 SDK 即可解释与访问文件中的全部超声内容（含坐标系刚体变换链 `crs_transforms`、物理参数、逻辑拼接组、伴生与旁路快照）。
- **单写与不可变**：保持单写者，不支持采集中读取增长文件；原始文件与旁路派生文件封存后均彻底不可变（Write-Once，[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)、[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)）。
- **明确排除**：执行期进程内分发与上位机内存池（`Batch-of-SoA`）归调用方；UI/Workflow、保存按钮/弹窗、任务准入/合格判据、设备控制、扫描复现、包络/滤波/成像与复杂闸门分析、激光点云、标注与缺陷成果（归 UMS）、额外导出（图片/CSV/打包）均不在范围。

<a id="ret-01"></a>
### RET-01：保留内容、状态与部分成果〔确定〕

- **保留模式分期收口（[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）**：逻辑架构认可全波（`full_wave`）、仅特征（`FeatureOnly`）与逐帧流式混合保留（`wave_and_feature`）三种合法业务模式；**Core 首版聚焦 `full_wave` + 伴生/旁路 C 扫快照**，`FeatureOnly` 与 `wave_and_feature`（含流式硬件特征表与选择性留波多态槽位状态）留待 M4 统一设计，避免首版出现契约与磁盘格式脱节。仅特征采集封存后不可被离线重算覆盖。
- **状态分离与部分成果**：在 `full_wave` 下原始波形槽位使用 [STA-01](#sta-01) 单一有效位区分有效（含有效零值）与无效/缺失（未来选择性留波在 M4 单独设计多态状态，不压进 1-bit 位图）。`Scan` 显式记录结束状态（`NORMAL_COMPLETE / USER_EARLY_STOP / FAULT_ABORTED / CANCELLED_EMPTY`），配合文件内已声明未采集的空 `Region` 实体共同表达部分成果与缺口。正常封存须满足非空对象约束（[LIF-01](#lif-01)）；保存成功不证明扫描完整或检测合格。

<a id="rel-01"></a>
### REL-01：必要关系、逻辑拼接组与自包含解释〔确定〕

- **区域、逻辑拼接组与复检关系（[ADR-0013](decisions/0013-region-relations-and-subset-scope.md)、[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）**：
  - `Region` 为文件内轻量独立实体（`region_id`、`name`、可选包围盒/参考系标识与扩展，不内置 CAD/树形环检测），与 `Scan` 保持 **M:N 引用**（未采集区域合法留空）。
  - **多区域拼接逻辑组（`ScanGroup`）**：支持在容器层显式声明多个 `Scan` 共同组成一个逻辑拼接整体（如主拼接检测面，含公共 `crs_ref` 与成员角色），与独立复检/验证 Scan 清晰区分，同时维持底层各 Scan 原始波形独立访问不自动融合。
  - **多目标与可选跨文件复检引线**：Scan 通过 `reinspection_targets[]` 数组指向一个或多个原 Scan/Region（支持跨越拼接接缝复检），并预留可选轻量跨文件 `target_file_uuid` 与容器级 `continuation_of_file_uuid`（纯元数据溯源指针，不引入跨文件联合查询引擎，完整多文件组织仍归 `D-19`）。
- **自包含模式解释与曲面几何（[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）**：单晶与相控阵采用**按扫描类型独立清晰的 Schema**，实行 **“最小解码必填核（强类型 C11 结构体）+ DICONDE（ASTM E2339 / E2663）& NeXus 强类型可选物理表（含水浸/喷水、多探头楔块、2D-TCG、TOFD PCS、增益三分解，JSON Schema 宽容演进）+ 容器级坐标系变换链 `crs_transforms` + 轻量参数化曲面几何（平面/柱/球/锥/弯头环面或带哈希外部参考，禁点云/网格）+ `VendorExtension`”**。

<a id="snap-01"></a>
### SNAP-01：Write-Once 伴生快照与版本化旁路派生容器〔确定〕

- **原始文件 Write-Once 与按 Scan 多次追加伴生快照（[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）**：SDK Core 支持在**原始文件封存前的 `FileOpen` 态按 Scan 多次追加不可变伴生 C 扫快照**（避免全 Run 末尾内存积压或末段崩溃丢前段快照），封存后严禁原地修改或热替换。
- **统一快照模型与版本化旁路派生容器（[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）**：伴生快照与离线派生快照共用同一模型：支持规则 2D 栅格或稀疏点表、**绑定 1..N 个源 Scan（支持整件多区域拼接大图）**、支持**共享或按层独立 `status`/`source`**（满足多闸门独立状态与多来源追溯，[ADR-0014](decisions/0014-configurable-selection-and-snapshot-source.md)）、记录实际采用参数（含可选分段参数记录）。离线派生写入独立 Write-Once 旁路容器（`file_role = DerivedSnapshot`，根部强绑定 `source_file_uuid`），更新优先采用**不可变版本化文件名 + `fsync` 原子指针切换**，规避 Windows 边看边重算的共享锁冲突。
- **来源不可篡改**：已保存快照追溯实际来源，多回波代表选择策略变化不得反向篡改历史来源；在线设置曾变更且无分段历史时不得用最后一组冒充全图。

<a id="access-01"></a>
### ACCESS-01：两层寻址、底层来源与扩展层多回波选择〔边界已定，扩展层后置〕

- **五类重点访问场景（[ADR-0013](decisions/0013-region-relations-and-subset-scope.md)）**：浏览已保存 C 扫快照、C 扫选点取 A 波形、区域批量读波形/取值、按 B/D/S 等布局批量读取、分批遍历整次扫描。物理分块支持可配置 `(F_chunk, K_chunk, S)` + 独立大块帧元 `F_meta_chunk`（离散帧清单合并解码于 v0.2 增量补齐）。
- **两层寻址分工（[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）**：
  - **SDK Core 原生寻址**：按触发序号连续区间交付每组稠密样本与位图，并针对启用 `CellCoord[Frame]` 的 Scan 在 `complete_scan()` 写出不可变排序索引 `frames/cell_index`，支持百 GB 文件 **`O(log N)` 毫秒级**查回选定离散单元的全部 `0~N` 帧号（不违背 `CAP-01`）。
  - **独立可选扩展层（3D 索引与多回波选择，`D-17`，归 M4）**：仅消费 Core 只读 API，基于原始 3D 坐标与 `crs_transforms` 按需构建独立旁路空间索引，按 `(x, y, z)` 查出 `0~N` 条候选并执行统一可插拔代表选择策略。
- **规范数据子集**：Core 支持按选定 `Scan`、基于离散单元或布局的空间区域、通道/声束/收发组合、波形样本窗口提取规范子集，保留必要解释与来源；不附带图片/CSV 导出或打包。

<a id="meas-01"></a>
### MEAS-01：独立选峰扩展的基础窗口取值〔已移出 Core 归 M4 扩展层〕

明确窗口内的基础幅值与位置/时间取值（如峰峰值、前沿取值）**已移出 SDK Core，归属独立可选扩展层**（只消费 Core 只读 API，不进入 Core 文件格式与写入路径，`D-18`）：

- 仅接收文件输入；不做深度/厚度转换、包络滤波、同步跟随门或跨波形跟踪。
- 区域批量取值保持请求区域的位置对应，逐点返回数值与状态，不把损坏/解码/I/O 错误伪装为普通无效点。
- 前沿取值同时返回**同一点的位置/时间与对应幅值**（[ADR-0012](decisions/0012-basic-access-confirmed-and-deferred.md)），保留取值条件与输入来源；具体判据待用户统一提供算法参考。

## 2. 逻辑模型、中立容器与物理引擎参考抽象

<a id="logical-model"></a>
### 2.1 对外中立容器与分模式 Schema 模型（现行）

SDK 对外数据组织采用 **中立交付容器外壳（主采集容器 / 版本化旁路派生容器）+ 轻量 M:N `Region` + 逻辑拼接组 `ScanGroup` + 分扫描类型独立 Schema**（[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)、[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）：

```text
PrimaryFile（file_role = Acquisition；不变 file_uuid；可选 workpiece / run / continuation_of_file_uuid / crs_transforms）
  ├─ Region 集合（文件内轻量独立实体：region_id、name、可选包围盒/参考系；可合法留空）
  ├─ ScanGroup 集合（可选逻辑拼接组：显式声明多 Scan 构成拼接整体与公共 crs_ref）
  ├─ Scan 集合（正常封存需 >=1 个 COMPLETED Scan；允许 cancel_empty_scan 取消 0 帧空 Scan）
  │    ├─ 模式 Schema 标识：SingleProbe / PhasedArray（首版 full_wave）；预留 FMC / FeatureOnly
  │    ├─ EndStatus：NORMAL_COMPLETE / USER_EARLY_STOP / FAULT_ABORTED / CANCELLED_EMPTY
  │    ├─ 引用 region_refs[0..M]（M:N）与 reinspection_targets[]（多目标，可选跨文件 target_file_uuid）
  │    ├─ 固定采集解释（不可变）：强类型最小解码必填核 + DICONDE(E2663)/NeXus 可选物理表（水浸/多探头/2D-TCG/PCS）
  │    │                      + 参数化曲面几何 + VendorExtension
  │    └─ 帧观测主体：
  │         ├─ 波形流组 g/*：samples[E, K_g, S_g]（(F_chunk, K_chunk_g, S_g) 分块）+ LSB-first 位图 valid
  │         └─ 大块解耦帧元 frames/meta（独立 F_meta_chunk）：位置/pos_valid/逐轴掩码/同步等级/界面波声时/CellCoord/aux
  │            + 可选排序索引 frames/cell_index（complete_scan() 写出，O(log N) 查回）
  └─ [可选] 采集期伴生 C 扫快照集合（FileOpen 态按 Scan 多次不可变追加，支持绑定 1..N Scan 与按层独立状态/来源）

DerivedSnapshotFile（file_role = DerivedSnapshot；独立 Write-Once 旁路容器，强绑定 source_file_uuid）
  └─ 离线派生 C 扫快照集合（同构支持 1..N Scan 与按层状态/来源；版本化文件名 + 原子指针切换避开 Windows 共享锁）
```

### 2.2 原始波形物理引擎参考抽象

下表保留为**共享底层物理 I/O 引擎**在承载原始波形模式（单晶 / PA / 后续 FMC）时的参考抽象（[ADR-0001](decisions/0001-stream-groups.md)）：

| 符号/术语 | 含义 |
|---|---|
| `Scan` | 一次扫描主体；持有固定方案、模式解释、局部 Frame 轴与双槽提交记录，不等于网格或图像 |
| `EventDefinition` / `e` | 固定方案中的发射事件槽位；跨帧复用，不是逐帧发射快照 |
| `WaveformStream` / `k` | 固定事件下固定接收输出的跨帧序列，Scan 内身份唯一；不必等于硬件通道 |
| `StreamGroup` / `g` | 同构流组：组内各流 dtype、样本数 `S_g`、样本表示与采样间隔一致，逐流差异以流表保存；每流静态属于唯一一组，组内序号 `q` |
| 组解释 | 通道组（单晶）、PA 声束集或 Tx×Rx 矩阵（后续 FMC）；解释属于流组 |
| 大块帧元表 | `frames/meta`：Scan 内固定打包的每帧一行定长记录（位置、`pos_valid`/逐轴掩码、同步等级、可选界面波声时、`CellCoord` 与 `required`/`nullable` 附加列），独立 `F_meta_chunk` 分块 |
| `Frame` / `n` | 一次结构闭合的组合记录及零起点索引，包含各流组第 n 行与帧元第 n 行 |
| `N` / `E_x` / `N_r` | 提交记录权威完整前缀长度（u64）/ 物理 dataset extent（可大于 N）/ 恢复模式验通前缀长度 |
| `B` / `K` / `K_g` | Batch 帧数（B≥1）/ Scan 流总数 / 流组 g 流数；PA 声束数记为 `N_b` |
| `S_g` / `τ_g` / `s` | 流组 g 固定样本数、原始 dtype 与样本索引（单流引用作 `S_k`、`τ_k`） |

逻辑身份为 `(Scan,n)`、`(Scan,n,e)`、`(Scan,n,k)`、`(Scan,n,k,s)`，按 `(g,q)` 定位存储与 Core I/O；接收输出必须辨识单接收阵元或固定接收法则合成波形，不得从 shape 猜测。

<a id="scan-01"></a>
### SCAN-01：中立文件容器、Region、ScanGroup 与独立 Scan〔确定〕

- 文件须支持枚举独立 `Region` 实体、逻辑拼接组 `ScanGroup` 与 `Scan` 集合；工件与 Run 为可选元数据。每个 `Scan` 独立持有模式 Schema、固定定义、结束状态（`EndStatus`）、Frame 轴与双槽提交记录；同文件内不同 `Scan` 不隐式复用定义。
- **新建 Scan 与不可重开追加（`D-15` 已关闭）**：分块、停止后重新扫描、复扫、精扫、换探头、重装、重标定或固定定义改变须创建新 Scan；段内暂停留在同一 Scan 内。同一未封存 Writer 会话可顺序完成当前 Scan 后创建下一 Scan（不支持交错写多个活动 Scan）；**文件封存或干净关闭后不支持重开追加原始波形或新原始 Scan**，离线派生写入 Write-Once 旁路容器，跨文件续扫/复检通过可选 `continuation_of_file_uuid` / `reinspection_targets[].target_file_uuid` 留痕（完整多文件联合组织归 `D-19`）。

<a id="scan-02"></a>
### SCAN-02：文件内 Region 实体、ScanGroup 与引用约束〔确定〕

按 [ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md) 与 [ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)，文件内 `Region` 为轻量元数据实体（`region_id`、`name`、可选包围盒/参考系标识与扩展，不含 CAD 引擎或树形环检测），与 `Scan` 构成 **M:N 引用**（未采集区域合法留空）；可选 `ScanGroup` 显式组合多个 Scan 为逻辑拼接整体；`reinspection_targets[]` 支持多目标文件内复检（拒悬空引用）及可选跨文件 `target_file_uuid` 元数据引线。

<a id="rec-01"></a>
### REC-01：共同记录身份〔确定〕

原始波形路径下，Scan 内所有流共用共同 Frame 轴；采集层归组并一次提交完整 Frame 或批次，SDK 不等待逐流拼装、不做时间配准或帧号回绕展开。共同 Frame 轴与重复位置值都不合并 Frame 身份、也不证明规则网格、空间邻接或运动同步；无有效数据的波形槽位使用 [STA-01](#sta-01) 有效位与零填充表达。

<a id="rec-02"></a>
### REC-02：计数、extent 与边界〔确定〕

`N` 范围为 u64（`0 <= n < N`），所有计数、索引、切片与字节长度运算必须防 32 位静默截断或溢出。物理 dataset extent `E_x`、fill value 与提交记录权威计数 `N` 严格区分：不得暴露 `n >= N` 尾部；必要对象在 `[0, N)` 内缺行或关联断裂时必须报结构错误，不得静默缩短宣称完整。

## 3. 身份、版本与元信息

<a id="id-01"></a>
### ID-01：解释身份〔确定〕

文件必须携带可识别的容器角色（`Acquisition` / `DerivedSnapshot`）、容器格式版本（`format_major.format_minor`）、**SDK 分配的不变 `FileInstanceUUID`**（旁路容器强绑定 `source_file_uuid`）、`Scan`/`Region`/`ScanGroup`/快照稳定 ID（工件与 Run 为可选元数据）、**采集模式 Schema 身份与独立 Schema 版本**（`SingleProbe`/`PhasedArray`，预留 `FMC`/`FeatureOnly`）和**物理布局身份**。文件公共描述与 Scan 专属描述作用域严格隔离，避免跨属性/JSON/DCPL 冗余双真理源。读取器遇不理解的 `format_major`、未知必要能力或未知模式 Schema 必须明确拒绝（[SDK_CONTRACT.md](SDK_CONTRACT.md#versioning)）。

<a id="id-02"></a>
### ID-02：必要能力与可选扩展〔确定〕

区分**影响当前请求解释的必要能力位（`required_features`）/filter/结构编码**与**可安全跳过的可选扩展（`optional_features` / 未知可选 JSON 键）**：未知可选扩展可跳过；未知必要能力位、语义或缺失解码器不得静默忽略。

<a id="meta-01"></a>
### META-01：公共描述与带类型/版本的内容〔确定〕

元信息采用 **最小解码必填核（强类型 C11 结构体）+ ASTM E2339/E2663 & NeXus 可选物理表（机读 JSON Schema）+ 带 `(vendor_id, schema_uri, schema_version)` 的可选 `VendorExtension`**（[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）。不得把关键解码或采样解释藏进无约定扩展字典。

## 4. 波形、状态、位置与参数（原始波形存储契约）

> 说明：本节 `WAV-*` 与 `STA-01` 约束实际保留原始波形的采集路径；预留的 `FeatureOnly` 与 `wave_and_feature` 留待 M4 展开（[RET-01](#ret-01)）。

<a id="wav-01"></a>
### WAV-01：流组内固定、支持 dtype 与自解释〔确定〕

在原始波形物理抽象中，每个流组 `g` 的逻辑样本形状为 $X_g \in \tau_g^{N\times K_g\times S_g}$。`S_g`、`τ_g`、样本表示与采样间隔在组内一致并在所属 `Scan` 内固定，逐流差异以流表保存；跨组可异构（单流可独占 `K_g = 1`）。

- **首版支持 `dtype`（[ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md)）**：`{i8, u8, i16, u16, i32, u32, f32}`，显式拒绝 `f64` 与复数类型。
- **`SignalDescriptor`（[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）**：固定描述须完整且无歧义地包含位宽/dtype、有效 ADC 位、`lsb`/`msb` 移位与符号扩展顺序、线性/`log_db` 标度模式、零点/比例/满幅与浮点饱和阈值、采样步长与原始 `adc_sample_rate_hz`/峰值压缩模式、起点延迟与时间零点参考（支持水浸 `surface_interface` 关联逐帧界面波声时），以及完整信号处理层次标签，确保离线无歧义复用 `Ingress Decode` 并保留 ADC 饱和证据。

<a id="wav-02"></a>
### WAV-02：严格接收与无损保存〔确定〕

`valid=1` 的波形必须与所属流组的固定长度和 `τ_g` 严格一致；SDK 校验身份、shape/dtype、容量与引用，不做业务幅值或成像合法性判定，也不隐式截断、补齐、重采样或数值转换。`valid=0` 的槽位可省略样本（稠密缓冲对应输入被忽略；Writer/Scan 级严格模式下出现非零样本则拒绝整个写调用）。标记有效且通过校验的整数样本按原生数值语义无损回读；**`f32` 按 IEEE-754 逐位无损保真**（不规范化 `NaN` payload 或改写 `-0.0`）。

<a id="sta-01"></a>
### STA-01：单一有效性位图与零填充〔确定〕

仅用于实际保留的原始波形槽位 `(Scan,n,k)`，粒度为整条波形（1 bit：`valid=1` 或 `valid=0`）：

- **显式提交完整位图（[ADR-0003](decisions/0003-explicit-validity-bitmap.md)、[ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md)）**：存储层与 C11 ABI 统一采用 **LSB-first packed bitset**（每帧每组 `ceil(K_g / 8)` 字节，高尾部位强制清零并校验）。每次写调用须为全部 Frame 的全部槽位给出有效位；缺失、长度不符、尾部位非零或身份不匹配时拒绝整个调用；严格模式按 Writer/Scan 选项开启。
- **有效全 0 vs 无效零填充**：`valid=1` 时即使全 0 样本也视为真实回波无损保存；`valid=0` 逻辑上呈全 0 填充值且交付时与位图一同返回、不跳过槽位，禁止仅凭全 0 推断无效或把填充值当作真实回波。存储损坏或 I/O 错误绝不降级为 `valid=0`。

<a id="pos-01"></a>
### POS-01：采集时位置绑定〔确定〕

支持无空间位置的纯时间/顺序扫描（不伪造零坐标）。需要空间的扫描中，**波形有效但位置获取失败时必须保全有效波形**，并通过显式 `pos_valid = 0` 标记位置未知/无效（禁用 `NaN` 猜无效，无效时位置槽位零填充）；`ENCODER_I64` 额外提供逐轴有效掩码 `pos_axis_valid_mask` 支持单轴有效/未接轴分离（[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）。位置绑定严格按 Frame 索引，不靠时间戳、浮点相等或最近邻搜索；历史采集位置不可被后处理静默覆盖。

<a id="pos-02"></a>
### POS-02：大块帧元表、姿态数学约定、同步等级与 `CellCoord`〔确定〕

- **位置模式、姿态约定与同步等级（[ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）**：`Scan` 静态声明无位置（`NONE`）或 5 种内置空间位置模式之一（`ENCODER_I64` / `CARTESIAN_2D_F64` / `CARTESIAN_3D_F64` / `POSE_6D_EULER_F64` / `POSE_6D_QUAT_F64`，取消 `CUSTOM_STRUCT`），`POSE_6D` 强制声明内/外旋、旋转顺序与变换方向；配套 Scan 级默认同步等级（可选帧级覆盖）与容器级 `crs_transforms` 刚体变换链。
- **可选离散 `CellCoord[Frame]` 与排序索引**：定长整型 `int32[1..3]` + `cell_valid` 无归属标记（附可选物理原点/步长/参考系），无规则布局时省略，不做浮点分箱；启用时于 `complete_scan()` 写出不可变排序索引 `frames/cell_index`。
- **帧级附加列合并大块存储**：时间戳、来源触发 ID、理论坐标、扫查速度以及标准语义列 `region_index` / `pass_index` / `scan_direction` 等，与位置/`CellCoord` 一并静态打包至单一紧凑行结构 `FrameMetaRow`，按独立大块 `F_meta_chunk`（默认 8192 帧）存储，按列标明 `required`/`nullable`（合并为 `aux_valid_mask` 位掩码），同 Frame 同步写入、禁晚到补写。

<a id="pa-01"></a>
### PA-01：唯一帧位置与派生声束解释〔确定〕

PA 声束集第 `n` 帧原始关系为 `Frame_n = (P_n, {W_n,b}, 状态与关联)`，**同帧全部 `N_b` 个声束共用唯一帧级原始位置 `P_n`**，不为每条声束重复复制原始位置；声束空间定位依赖 `P_n + crs_transforms + 探头/楔块几何 + 对应聚焦法则`（`focal_law` 分离 `tx_probe_id`/`rx_probe_id` 支持 DMA/DLA 双阵，物理表可记 `law_prf_hz`/`frame_rate_hz` 支撑高速运动偏斜补偿）。束号静态关联事件与接收聚焦法则，派生声束坐标不覆盖 `P_n`。多独立运动探头位置模型归 `D-13`。

<a id="par-01"></a>
### PAR-01：固定采集定义的作用域与复用〔确定〕

Scan 共享设置、每个事件设置、流组共享采样表示与组内流表均在所属 Scan 作用域内固定并只保存一次（预定程序周期循环不属于参数修改）。方案、流组划分、流长度/dtype 或采样解释发生真实变化须新建 Scan（[SCAN-01](#scan-01)），不可维持旧 Scan 身份或记录逐帧 `config_index`。在线特征门参数变动通过快照分段参数记录或变更标记表达（[SNAP-01](#snap-01)）。

<a id="par-02"></a>
### PAR-02：旧动态快照字节区〔已替代〕

`data + offsets` 动态快照字节区已被 [PAR-01](#par-01) 取代，仅保留编号作历史追踪，不再使用。

<a id="fmc-01"></a>
### FMC-01：固定 Tx/Rx 映射与覆盖〔确定语义，FMC 模式预留〕

Tx×Rx 矩阵是流组解释（`FMC` 模式在首版 Schema 类型枚举中保留预留口，不展开首版工程字段）：有序发射集合 `I`、接收集合 `J` 与显式映射 $\pi$ 定义 $M_n[i,j] = X_{\pi(i,j)}[n,:]$（首版单矩阵限于单个流组；跨组及部分矩阵归 `D-14`）。声明为完整矩阵时必须覆盖全 `I×J`，有序对映射唯一且与事件发射/接收输出身份一致，禁止互易对复用或从目录顺序推断。

<a id="fmc-02"></a>
### FMC-02：矩阵访问与异构结果〔确定语义，FMC 模式预留〕

选定 Tx/Rx 单元同构时可于上层视图交付 `[Tx,Rx,Sample]`（Batch 加帧轴）及有效性位图（共同时间轴须采样解释一致）；异构时返回带 Tx/Rx 身份的分单元结果，不隐式转换。

## 5. HDF5 组织边界与正式写入保护机制

<a id="map-01"></a>
### MAP-01：逻辑语义、三维波形分块与大块帧元解耦〔确定〕

写出文件使用 HDF5 2.x 库（非 SWMR）并限定 `libver` 为 `v1.10–v1.14` 兼容格式（[ADR-0005](decisions/0005-file-format-range.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)，单 chunk `< 4 GiB`），物理布局完全服务于读写效率（详见 [WIRE_FORMAT.md](WIRE_FORMAT.md)）：

- **三维波形分块 + 大块帧元解耦**：原始波形支持可配置 `(F_chunk, K_chunk, S)`（单波形 `S` 维不切分，默认 `K_chunk = K`、1–4 MiB 目标块）；全部帧级元数据脱离 `F_chunk` 合并打包至 `frames/meta`（独立大块 `F_meta_chunk`，默认 8192 帧），彻底消除微块碎裂与校验膨胀。
- 下列逻辑边界必须可由 SDK 完整独立解释：

| 逻辑对象 | 逻辑范围与职责 | 规则与 wire 落点 |
|---|---|---|
| 容器角色、Region、ScanGroup 与 Scan | `file_role`、`file_uuid`（旁路绑定 `source_file_uuid`）、可选工件/Run/续扫引线/`crs_transforms`、轻量 M:N `Region`、逻辑拼接组 `ScanGroup`、Scan 枚举与 `EndStatus` | `SCAN-01/02`、`ID-01`；`WIRE_FORMAT` §2–§5 |
| 解释身份与模式 Schema | 容器版本、模式类型与独立 Schema 版本（`SingleProbe`/`PhasedArray`，预留 `FMC`/`FeatureOnly`）、最小解码核与可选物理表 | `ID-01`、`META-01`、`REL-01`；`WIRE_FORMAT` §6 |
| 波形主载荷与位图 | 原始流组样本 `[E,K_g,S_g]`（`(F_chunk, K_chunk_g, S_g)` 分块）与 `[E,ceil(K_g/8)]` LSB-first 位图 | `WAV-01`/`STA-01`；`WIRE_FORMAT` §7 |
| 大块帧元与 `CellCoord` 索引 | 合并大块 `frames/meta`（`F_meta_chunk`）与 `complete_scan()` 不可变排序索引 `frames/cell_index` | `POS-01/02`、`ACCESS-01`；`WIRE_FORMAT` §8 |
| 写入保护、外部 WAL 与双槽提交 | 外部临时 `.uss.wal` 增量追加（封存删）、`wave_sums`/`meta_sums` 单一 `stored_xxh3`、固定 240B 双槽 `commit`、双槽 `/lifecycle` | `WRT-02`/`LIF-01/02`/`MAP-02`；`WIRE_FORMAT` §9 |
| 伴生与版本化旁路快照 | 统一快照模型（1..N Scan、2D 栅格/稀疏点表、共享/按层状态与来源）；`FileOpen` 态多次追加伴生快照，离线写版本化旁路容器 + 原子指针 | `SNAP-01`；`WIRE_FORMAT` §10 |

`E_x > N` 预分配不等于已提交；重写含已 Flush 数据的压缩 chunk 时 HDF5 会原地覆写或复用空间导致崩溃损坏（[ADR-0002](decisions/0002-durability-and-failure.md)）。

<a id="map-02"></a>
### MAP-02：正式写入保护机制（非 SWMR 只写一次 + 外部临时 `.wal`）〔确定〕

已由 [ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md) 修订减痛为现行写入保护基线（须在 M2 完成 Extensible Array `>= 20,000` 块 + dense group + 大快照写入的随机 SIGKILL 隔离恢复验证，`D-05`）：

1. **物理块只写一次（非 SWMR 单句柄）**：Writer 全程维持单一非 SWMR HDF5 句柄，不再跨 Scan 切换 SWMR 或关闭重开句柄；写端在全局锁外组装整块、压缩并计算单一 **`stored_xxh3`**，经 `H5Dwrite_chunk` 只写一次（绕过块缓存）；`complete_scan()` 将尾块补零写一次并写出可选排序 `frames/cell_index`。
2. **外部临时顺序追加 `.wal` + 双槽提交**：Flush 时仅将自上次 Flush 以来的未满条带增量帧顺序追加到同目录临时文件 `<file>.uss.wal`（零预分配死空间、零重写放大），`H5Fflush(.h5)` 后写入双交替槽 `commit`（240B 固定结构，含 `wal_committed_offset`）并再次 `H5Fflush`。高频 `flush()` 不强制 `fsync`（提供可选 `USS_FLUSH_SYNC` 标志）；**低频 `complete_scan()`、`seal()` 与旁路提交强制 `fsync`/`FlushFileBuffers`**；`complete_scan()` 重置 `.wal`，`seal()` 成功后删除 `.wal`。
3. **强制独立子进程原地只读恢复**：`LIF-02` 在独立受限只读恢复子进程中执行，联合读取 `.h5`（经公开 `H5FDregister` 只读修补 VFD 原地清状态位并处理 `EOA > EOF`，绝不复制或修改源文件）与 `.wal`，彻底阻断畸形 HDF5 崩垮宿主 `.NET` 进程；双槽提交全毁则该 Scan 判不可恢复（`N_r = 0`）。
4. **有界 `staging_budget` `push` 读与锁外并发**：`push` 在 `staging_budget` 内先锁外并发读入并验完全部 `stored_xxh3` 再解码写入目标（单遍、有界内存、失败目标不变）；超预算默认要求分批或显式传两遍/流式标志（[SDK_CONTRACT.md](SDK_CONTRACT.md#core-io-batch)）。

## 6. 写入、持久化与 Write-Once 生命周期

> 原始主文件与旁路派生文件均遵循 Write-Once 封存不可变；完整状态转移图见 [SDK_CONTRACT.md](SDK_CONTRACT.md#lifecycle-state)。

<a id="wrt-01"></a>
### WRT-01：提交单元、前置校验与写失败态〔确定〕

- **前置整批校验**：每次写调用的 Frame 批次（属于单一活动 Scan）必须作为整体在写入文件或推进提交记录前完成校验；任一项不合格则整个调用拒绝，前缀不变，提交状态报告 `NOT_COMMITTED`。
- **同步消费与写失败态**：允许阻塞、无取消，输入缓冲在返回后不保留借用。写/Flush/完成/快照/封存发生任何 I/O 错误时按 [IO-01](#io-01) 失败并使 **Writer 进入写失败态**（**一律禁止原位重试或继续追加**，且 **`seal_with_failure` 禁止向已报错句柄补写未 Flush 内存尾部**，[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）。

<a id="wrt-02"></a>
### WRT-02：提交记录、完整前缀与不可变历史〔确定〕

每个 `Scan` 独立维护固定 240B 双槽提交记录（权威可见帧数 `N`、`.h5` 块计数、`.wal` 提交偏移与 `def_xxh3`），它是可见范围的唯一权威（`E_x` 仅物理上界）。已提交物理块严禁重写或复用空间，每个物理块记录单一 `stored_xxh3` 作为独立完整性核对依据；已提交历史不得修订或晚到补写。

<a id="wrt-03"></a>
### WRT-03：显式 Flush 与低频 `fsync` 边界〔确定〕

普通写入不承诺立即落盘。显式 `Flush`（以及隐含提交的 `complete_scan` / `seal`）返回成功后保证：**此前全部已写入数据及其解释元数据，在之后任意时刻发生进程崩溃后，均能由 [LIF-02](#lif-02) 独立恢复子进程完整恢复并通过 `stored_xxh3` 校验。**

- **崩溃与同步分层（[ADR-0008](decisions/0008-process-crash-scope.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）**：高频 `flush()` 覆盖进程崩溃（交给 OS 页缓存，提供可选 `USS_FLUSH_SYNC` 标志）；低频 `complete_scan()`、`seal()` 及旁路快照提交/指针切换强制执行 `fsync`/`FlushFileBuffers`（含 POSIX 父目录同步），消除已封存/替换文件因断电变 0 字节的风险。

<a id="io-01"></a>
### IO-01：调用级强原子性〔确定〕

每次读写调用是一个成功/失败单元，遇 I/O 错误、越界/空选择、容量不足或损坏必须整体失败并返回稳定错误码（不得悄悄缩短数量交付部分结果）：

- **`push` 读失败**：在 `staging_budget` 内（或显式 `TWO_PASS` 模式）保证调用者目标缓冲逐字节不变；超预算调用若未传显式标志则修改前拒绝（[SDK_CONTRACT.md](SDK_CONTRACT.md#core-io-batch)）。
- **写失败**：不新增提交，已提交数据经校验核对保持不变，Writer 进入失败态。
- **提交状态与绑定隔离**：写入类调用独立返回 `COMMITTED / NOT_COMMITTED / UNKNOWN`；原生已提交但语言绑定层封装失败时不得伪装成未提交供调用方盲重试。

<a id="lif-01"></a>
### LIF-01：Scan 完成/取消空 Scan、严格非空封存与 Write-Once〔确定〕

- **文件三条生命周期**：① 初始化 → 顺序写入 Scan（含可选 `cancel_empty_scan()` 放弃 `N == 0` 活动 Scan，以及 `FileOpen` 态按 Scan 多次追加不可变伴生快照与 `ScanGroup`）→ 正常 `seal()`（需 `n_scans_completed >= 1`，含 `fsync` + `H5Fclose` + 删 `.wal`）；② 写失败态 → `seal_with_failure`（需已有至少 1 个已完成 Scan 或已提交帧，禁封存空壳、禁补写未 Flush 尾部、禁降级已完成 Scan）或 `abort_and_close`；③ 未封存即关闭（含崩溃）→ 交 [LIF-02](#lif-02)。
- **Scan 生命周期与结束状态（[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）**：定义/初始化 → 追加（含段内暂停）→ `complete_scan`（`N >= 1`，`NORMAL_COMPLETE / USER_EARLY_STOP / FAULT_ABORTED`）或 `cancel_empty_scan`（仅限 `N == 0`，标记 `CANCELLED_EMPTY` 安全回退 `FileOpen`）。正常封存允许保留已声明未采集的空 `Region`。
- **Write-Once 不可变与不重开（`D-15` 已关闭）**：正常读取仅面向已封存文件；封存后彻底不可变，离线派生写入独立 Write-Once 旁路容器（Windows 版本化文件名 + 原子指针切换，[SNAP-01](#snap-01)）。

<a id="lif-02"></a>
### LIF-02：独立恢复子进程原地只读恢复〔确定〕

未正常关闭文件（含 `seal` 写完 `/lifecycle` 但 `H5Fclose` 前崩溃的文件）必须通过显式只读恢复模式处理（正常重开必须拒绝，绝不原地修改或复制百 GB 源文件）：

1. **强制子进程隔离与原地只读 VFD（[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）**：恢复必须在独立受限只读子进程中运行，防止畸形/撕裂 HDF5 元数据触发内存越界拖垮宿主 `.NET` 进程；通过公开 `H5FDregister` 只读修补 VFD 在内存中清除 v3 superblock 偏移 `11` 状态位、处理 `EOA > EOF` 与跨 `[0..48)` 边界读并重算 `Jenkins lookup3`，保持源文件哈希逐字节不变。
2. **联合 `.h5` + `.wal` 逐 Scan 核验**：以每个 Scan 有效 `commit`（优先于未同步的 `/lifecycle`）确立权威前缀 `N` 并联合校验 `.wal` 增量记录与各物理块 `stored_xxh3`；双槽提交全毁则判该 Scan 不可恢复（`N_r = 0`），不凭 extent 猜长度，不连带缩短其他完好 Scan；损坏块绝不降格为 `valid=0`。

## 7. 读取语义与内存规模

<a id="read-01"></a>
### READ-01：独立和绑定访问〔确定〕

Core I/O 每次请求指定一个 `Scan`、连续帧区间 `(start_frame, count)` 及一个或多个流组；支持识别 `FileInstanceUUID`、枚举 `Region`/`ScanGroup`/`Scan`/快照（不可默认“第一个或最新 Scan”，不跨 Scan 自动拼接原始波形），以及通过 `frames/cell_index` 按 `CellCoord` `O(log N)` 查回 `0~N` 帧号。等效条件下返回相同数据，读取永不修改文件。

<a id="read-02"></a>
### READ-02：边界校验与整体拒绝〔确定〕

Core I/O 的空选择（`count == 0` 或空组清单）、帧越界、目标缓冲字节容量不足一律**整体拒绝**并返回明确错误码，严禁静默截断或补齐；`valid=0` 是正常数据状态（返回零填充和位图），I/O 或校验错误不降格为无效槽位。帧内流/声束/Tx/Rx/样本花式选择由调用方或可选上层辅助库在稠密结果上纯内存执行（不在 C11 存储 ABI 中维护）。

<a id="read-03"></a>
### READ-03：单一 `push` 读取原语与容量查询〔确定〕

Core C11 ABI 将分析读取与 Batch 消费合并为单一连续区间 `push` 读取原语（可选帧元/位置输出缓冲指针，传 `NULL` 跳过；离散帧清单于 v0.2 增量追加）。跨流组采用**每组独立稠密缓冲**交付 `[B,K_g,S_g]` 样本与 `[B,ceil(K_g/8)]` 位图，并提供块几何与字节容量查询 API 对齐上位机预分配池（如 UMS `Batch-of-SoA`），不得要求全扫描驻内存。

<a id="buf-01"></a>
### BUF-01：`push` 缓冲所有权与 `staging_budget`〔确定〕

Core C11 ABI **全面采用 `push` 所有权模型**（[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md) 已取消原生 `poll` 借用状态机与 `.NET` `borrow_generation`）：调用方提供可写缓冲与 64 位字节长度（适配 `Batch-of-SoA` 与 >2 GiB 非托管内存），Reader 关闭或其他读取永不使已交付数据失效；高层托管绑定可基于 `push` 自行分配托管/池化缓冲提供便利接口。SDK 内部按 `staging_budget` 严格控制暂存内存上限（详见 [SDK_CONTRACT.md](SDK_CONTRACT.md#core-io-batch)）。

<a id="cap-01"></a>
### CAP-01：超 RAM 访问与 `O(1)` 打开〔确定〕

支持大于 100 GB、工作集远超物理 RAM 的单文件：打开文件为 `O(1)`（不加载全量波形或全量 `sums` 表，不随 Scan 数或总帧数 N 线性增长）；读/写内部暂存受 `staging_budget` 与块组装上限严格约束；`CellCoord` 排序索引经 `O(log N)` 二分块读查回，不需全表驻内存。单 Frame 不提供帧内分块交付，单 Frame 或单条带超限显式拒绝。

## 8. 压缩与解码

<a id="cmp-01"></a>
### CMP-01：无损压缩与精简内置编码链〔确定〕

无损压缩须满足 [WAV-02](#wav-02)，且完整编码链与参数记录在标准 HDF5 filter 链，缺失解码器或不支持参数时明确报错。首版 SDK 静态内置且仅支持 **`none`**、**`shuffle + zstd`（默认 level 1–3）** 与 **`shuffle + lz4`（高吞吐可选，单块 `<= 1 GiB` 强约束 `n_blocks == 1`）**（`H5Z_FILTER_SHUFFLE`、`32015` Zstd、`32004` LZ4；静态 `H5Zregister` 并禁用外部动态插件加载，不内置 `deflate`），天然衔接 M4 GPU `nvCOMP` 解压。

<a id="cmp-02"></a>
### CMP-02：GPU 可选能力的声明〔确定，归 M4〕

CPU 解码可读是基础保证，GPU 直接解压为独立可选加速能力（`D-06`）：只有当“磁盘压缩块 → 传输 → GPU 解码＋预处理逆变换＋尾块”全链路与 CPU 解码逐值一致并通过端到端测量后，方可声明支持。

## 9. 运行时完整性核验与统一逻辑不变量

<a id="val-01"></a>
### VAL-01：运行时核验与离线测试报告解耦〔确定〕

按 [ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)，严格区分**运行时库核验**与**测试套件报告**：
- **运行时库**：① `open_reader` 执行 `O(1)` 头/角色/能力位/双槽 `/lifecycle` 校验；② 每次 `push` 读逐块核验 `stored_xxh3`、filter mask、位图尾部位清零与 `*_valid` 域值；③ 提供独立的流式 `uss_verify_file()`（有界 O(1) 内存全扫所有对象、索引与物理块 `stored_xxh3`）。任何校验不匹配均为硬文件错误，绝不降格为 `valid=0`。
- **测试报告格式**（`PASS / FAIL / NOT_RUN / BLOCKED / UNSUPPORTED`、Spec 哈希、test-only 标注）仅归验证套件（[SPEC_TEST_PLAN.md](SPEC_TEST_PLAN.md)），不耦合进运行时库数据结构。

<a id="invariants"></a>
### 本轮统一逻辑不变量

`U-01`–`U-16` 用于设计与验证追踪，不分配 wire 字段或错误码：

| 规则 | 必须保持的性质 | 细节入口 |
|---|---|---|
| <a id="u-01"></a>U-01 | HDF5 2.x 非 SWMR 写出 1.10–1.14 兼容格式；按扫描类型提供独立清晰 Schema，不靠 shape 猜测模式；不承诺 `h5py` 裸翻内部路径 | DOC-01、ID-01、MAP-01 |
| <a id="u-02"></a>U-02 | Scan/事件/流组采集定义在 Scan 内固定只存一次；固定程序循环不产生逐帧配置历史 | PAR-01 |
| <a id="u-03"></a>U-03 | 原始波形可追溯到 Frame、事件与接收输出（区分阵元与合成信号）；流静态属于唯一组；流不等同于硬件通道 | 逻辑模型、REC-01 |
| <a id="u-04"></a>U-04 | 流组内 dtype/长度/采样解释固定，组间允许异构，整数原生无损、`f32` 按位无损，完整无歧义保留 `SignalDescriptor` | WAV-01/02 |
| <a id="u-05"></a>U-05 | PA 同帧全部声束共用唯一帧级原始位置 `P_n`；显式 `pos_valid`/逐轴掩码、姿态约定、同步等级与 `crs_transforms` 刚体链 | POS-01/02、PA-01 |
| <a id="u-06"></a>U-06 | FMC 显式固定 Tx/Rx 映射，行列不互换，互易对独立；单矩阵限于单个流组（首版预留） | FMC-01 |
| <a id="u-07"></a>U-07 | 矩阵/流组/流/单波形共享同一来源；组内稠密交付，异构不强行补齐转换 | FMC-02 |
| <a id="u-08"></a>U-08 | 原始波形槽位采用单一 LSB-first packed bitset，写入显式提交并校验尾部位零；有效全 0 保真、无效零填充，错误不降格为无效位 | STA-01、WRT-01、LIF-02 |
| <a id="u-09"></a>U-09 | Core 连续 `push` 边界/容量校验整体拒绝；帧内选择留上层纯内存，保序保重复不改原始数据 | CORE-01、READ-02/03 |
| <a id="u-10"></a>U-10 | 波形、位图、大块帧元、`CellCoord` 排序索引与固定定义关联一致；位置失败保全有效波形且禁用 `NaN` 猜无效 | READ-01、POS-01/02、META-01 |
| <a id="u-11"></a>U-11 | Core 全走 `push` 所有权（有界 `staging_budget`、`O(1)` 打开）；原始与版本化旁路容器封存后均 Write-Once 不可变 | READ-01/03、BUF-01、CAP-01、SNAP-01 |
| <a id="u-12"></a>U-12 | 原始采集历史与伴生快照不可篡改，仅特征不可被覆盖；合规、算法、性能与恢复分开验证 | WRT-02、RET-01、VAL-01 |
| <a id="u-13"></a>U-13 | 中立容器分配不变 UUID，独立承载轻量 M:N `Region`、`ScanGroup` 与多 `Scan`；支持 `cancel_empty_scan` 且正常封存拒空壳；封存后不重开追加 | ID-01、SCAN-01/02、LIF-01/02 |
| <a id="u-14"></a>U-14 | 多 Scan 原始结果独立并存，不隐式融合或替代；多区域拼接通过显式 `ScanGroup` 与多 Scan 快照表达 | SCAN-01/02、READ-01、SNAP-01 |
| <a id="u-15"></a>U-15 | 双槽提交记录为可见范围唯一权威（全毁不可恢复）；非 SWMR + 外部 `.wal` + 低频 `fsync` + 独立子进程隔离恢复保障 `stored_xxh3` 验通；写失败禁重试禁补写未 Flush 尾部 | WRT-01–03、IO-01、LIF-01/02、MAP-02 |
| <a id="u-16"></a>U-16 | 进程内 HDF5 元数据串行、只读 chunk I/O 锁外并发；同一对象不并发；多进程只读已封存文件；写期间经 OS 文件 ID + 哨兵字节锁拒绝同/跨进程 Reader | CORE-01、BUF-01 |

<a id="open-items"></a>
## 10. 待定项登记与闭合门槛

下表是全库唯一 `D-01`–`D-19` 状态登记表（详细推进清单见 [DECISION_DIRECTIONS.md](DECISION_DIRECTIONS.md)）：

| 编号 | 当前状态 | 已定结论与剩余缺口 | 权威依据 |
|---|---|---|---|
| D-01 | **已闭合（Wire 1.0 r2 落盘）** | 大块合并 `frames/meta`（`F_meta_chunk`）、5 种内置位置模式（去 `CUSTOM_STRUCT`）、`pos_valid` + 编码器逐轴有效掩码、姿态约定、`crs_transforms`、同步等级、`CellCoord` + 排序索引及标准附加列已定 | ADR-0019 / 0021 |
| D-02 | **dtype 已闭 / 规模待事实** | 首发 `dtype` 已定 `{i8..u32, f32}`；仍需真实 UMS 设备最大 Frame 字节数、持续速率与全链路峰值内存预算 | ADR-0019 |
| D-03 | **布局已闭 / 权重待事实** | `(F_chunk, K_chunk, S)` + 大块 `F_meta_chunk` + `CellCoord` 排序索引已定（离散清单留 v0.2）；仍需五类场景权重与延迟/吞吐门槛 | ADR-0017 / 0021 |
| D-04 | **编解码与分块已闭 / M3 校准** | 内置 `none` / `shuffle+zstd`（默认）/ `shuffle+lz4`（单块 `<=1 GiB`）及默认 1–4 MiB 目标块已定；M3 按实测校准默认值 | ADR-0017 / 0019 / 0021 |
| D-05 | **机制已定 / M2 EA 压测复核** | 正式选定非 SWMR 只写一次 + 外部临时 `.wal` + 低频 `fsync` + 独立恢复子进程隔离；M2 须完成 Extensible Array `>=20,000` 块 + dense group + 大快照 SIGKILL 实测 | ADR-0018 / 0021 |
| D-06 | **后置（M4 可选）** | GPU `nvCOMP` 完整 filter 链解压一致性与端到端对比（不阻塞 Core M3） | CMP-02 |
| D-07 | **Wire r2 草案已出 / 待薄切片验证** | 单一 `stored_xxh3`、HDF5 `v1.10–v1.14` 兼容写出（取消 1.14 双实现门禁）、三轴版本解耦、`WIRE_FORMAT.md r2` 已就位；待 M2 C++20 薄切片实测收敛 | ADR-0005 / 0021 |
| D-08 | **已闭合** | LSB-first packed bitset（尾部位清零校验）、Writer/Scan 级严格模式已定 | ADR-0003 / 0019 |
| D-09 | **分层与必填核已闭 / 实机物理表待核对** | 最小解码核走强类型 C11 结构体，ASTM E2339/**E2663** & NeXus 可选物理表（水浸/多探头/2D-TCG/PCS）走宽容 JSON Schema；待对照首批单晶/PA 实机参数核对 | ADR-0017 / 0021 |
| D-10 | **极简合同已闭 / 紧接起草 `uss.h`** | `push`-only 单一读原语（去 `poll`/纯选择层）、`staging_budget`、`cancel_empty_scan()` 与状态机已定；紧接产出极简 `uss.h` | ADR-0010 / 0021 |
| D-11 | **已闭合（Wire 1.0 r2 落盘）** | 轻量 M:N `Region`（去树环检测）、逻辑拼接组 `ScanGroup`、多目标 `reinspection_targets[]`（含可选跨文件 `target_file_uuid` 轻引线）已定 | ADR-0017 / 0021 |
| D-12 | **已闭合 / Windows 前移至 M2** | C++20 + 极简 C11 ABI 静态单库（`H5dont_atexit`/低 `glibc`/`/MT`）+ `.NET`（`net10.0`/`net48`）+ 哨兵锁协议已定；Windows + `.NET 4.8` 烟雾闭环前移至 M2；Python 归 M4 | ADR-0020 / 0021 |
| D-13 | **明确后置** | 混合扫描与多独立运动探头位置模型 | ADR-0017 |
| D-14 | **明确后置** | HMC/PWI/Sparse 部分矩阵与跨组异构矩阵（`FMC` 预留） | ADR-0009 / 0017 |
| D-15 | **已关闭** | 段内暂停同 Scan；封存后不重开追加（跨文件续扫留 `continuation_of_file_uuid` 引线） | ADR-0016 / 0021 |
| D-16 | **已闭合（Wire 1.0 r2 落盘）** | 1..N Scan 绑定、多次追加伴生快照、共享/按层状态与来源、版本化旁路文件名 + 原子指针切换已定 | ADR-0017 / 0021 |
| D-17 | **独立扩展层（M4）** | 旁路 3D 空间索引与可插拔多回波代表选择（只消费 Core 只读 API） | ADR-0016 |
| D-18 | **独立扩展层（M4）** | 窗口选峰扩展（前沿成对输出位置/时间与幅值，等用户算法参考） | ADR-0016 |
| D-19 | **明确后置（已留轻量引线）** | 多文件集合解析与跨文件联合查询（Wire 1.0 已预留 `target_file_uuid` / `continuation_of_file_uuid` 元数据指针） | ADR-0015 / 0021 |

<a id="closure-gates"></a>
### 待定项的阶段闭合门槛

推进里程碑状态统一维护于 [SPEC_TEST_PLAN.md](SPEC_TEST_PLAN.md#milestones)：

| 阶段 | 须闭合的 D 项与硬性证据 |
|---|---|
| **M2（极简 `uss.h` 与代码驱动薄垂直切片）** | 产出极简 `uss.h`；构建 Linux x64 + **Windows MSVC（含 `.NET 4.8` 烟雾调用）** 静态自包含单库薄切片（非 SWMR + 外部 `.wal` + 锁外并发 `pread` + 哨兵锁 + 独立恢复子进程）；完成 Extensible Array `>=20,000` 块 + dense group + 大快照 SIGKILL 恢复实测（`D-05`）；补齐首批真实单晶/PA 设备字段与规模上限（`D-02`/`D-09`） |
| **M3（Core 首版全面验收）** | 完成单晶/PA 全波、逻辑拼接组、排序 `CellCoord` 索引、伴生/版本化旁路快照、`.NET 10` & `.NET 4.8` 绑定验收（`D-12`）；完成真实波形默认块/压缩校准（`D-03`/`D-04`）、>100 GB 超 RAM 与故障恢复门禁；`1.0-rc` 启用 `SONAME`/`abidiff` 门禁 |
| **M4（扩展、流式特征与后续）** | 逐帧流式混合保留（`wave_and_feature`）与 `FeatureOnly`、`FMC`、独立扩展层（`D-17`/`D-18`）、官方 Python 绑定、GPU `nvCOMP` 直接解压（`D-06`）及 `D-13`/`D-14`/`D-19` 按需演进 |

## 11. 契约修订流程

按“候选规则 → 正反样例 → 薄切片实测 → 修订契约”迭代；变更须注明需求依据、数据影响与旧实验适用性，理由写入 `docs/decisions/`（[ADR-0007](decisions/0007-documentation-structure.md)）。禁止在测试代码或外部文档维护隐含第二套规范。
