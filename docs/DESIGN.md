# 超声数据 SDK：需求、两层架构与设计收敛视图

状态：已依据 [ADR-0001～ADR-0021](decisions/README.md) 完成 Core 首版架构定型与减痛重构（Spec `0.3-draft` + [WIRE_FORMAT.md](WIRE_FORMAT.md) `1.0-draft r2`）；已准备暂停文档扩张，进入极简 `uss.h` 与代码驱动的 Linux/Windows 薄垂直切片实现，不修改或重跑既往实验。

本文维护产品定位、需求基线（`R-01`–`R-20`）、核心架构决定与审阅确认视图。数据与存储契约唯一定位于 [DATA_SPEC.md](DATA_SPEC.md)，首版工程合同位于 [SDK_CONTRACT.md](SDK_CONTRACT.md)，二进制布局规范位于 [WIRE_FORMAT.md](WIRE_FORMAT.md)，已采纳决定在 [ADR 目录](decisions/README.md)，剩余待补事实与 M2 清单集中在 [DECISION_DIRECTIONS.md](DECISION_DIRECTIONS.md)。

## 1. 产品全景与两层架构

SDK 是包含权威 schema 与规范化读写能力的单一超声数据存储产品，独立维护并开源。它面向 **UMS 保存与重开**、**其他扫描系统创建扫描数据**、**其他集成与外部分析完整读取**三类使用者，承担以文件为载体的跨系统数据交付（[ADR-0015](decisions/0015-cross-system-data-delivery.md)、[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)）。

```text
+-------------------------------------------------------------------------+
| SDK Core（C++20 核心 + 极简 push-only C11 ABI 静态单库；.NET 10 / 4.8）  |
|  · 中立交付容器：不变 UUID、轻量 M:N Region、逻辑拼接组 ScanGroup、     |
|                  多 Scan/EndStatus、cancel_empty_scan、跨文件复检引线   |
|  · 分模式独立 Schema：首版单晶/相控阵全波（预留 FMC/FeatureOnly/混合）  |
|  · 自包含解释：C11 强类型最小解码核 + DICONDE(E2663)/NeXus 可选物理表   |
|                （含水浸/2D-TCG/PCS）+ crs_transforms + VendorExtension  |
|  · 原生高效寻址：连续区间 push 读 + CellCoord 排序索引 O(log N) 查回    |
|  · 物理 I/O 引擎：HDF5 2.x 非 SWMR 写 1.10-1.14、波形 (F,K,S) 与大块    |
|                  帧元解耦、none/shuffle+zstd/shuffle+lz4、stored_xxh3、 |
|                  外部临时 .wal + 低频 fsync + 子进程隔离恢复 + 锁外并发 |
|  · Write-Once 生命周期：按 Scan 多次追加伴生快照 → 永久只读             |
+------------------------------------+------------------------------------+
                                     | 只消费 Core 只读 API（不进入 Core 文件格式与写入路径）
        +----------------------------+----------------------------+
        v                                                         v
+-------------------------------+                       +-----------------------------------+
| 独立可选扩展 ①：选峰基础取值   |                       | 独立可选扩展 ②：3D 索引与多回波选择 |
| · 明确窗口内峰峰值（M4）       |                       | · 按需构建旁路 3D 空间索引（M4）   |
| · 前沿点位置/时间 + 对应幅值   |                       | · 按 (x,y,z) 查 0~N 候选           |
| · 区域保形逐点状态（D-18）     |                       | · 可插拔代表选择策略（D-17）       |
+-------------------------------+                       +-----------------------------------+

[统一快照模型与版本化 Write-Once 旁路分离]
  原始采集文件（Acquisition）：顺序写 Scan (支持 cancel_empty_scan) + FileOpen 态多次追加 1..N Scan 伴生快照 ─→ seal 只读
                                                                                                                  │
  离线派生快照（DerivedSnapshot）：版本化 Write-Once 旁路文件（强绑定 source_file_uuid，原子指针切换防 Windows 锁冲突）

[明确排除（留待调用方/UMS）]
  · UI / Workflow / 设备控制 / 扫描复现 / 执行期进程内分发与上位机内存池（Batch-of-SoA 由调用方管理）
  · 激光点云 / 包络滤波或成像引擎 / 标注与缺陷分析成果 / 额外导出（图片/CSV/打包）
```

**自描述边界**：仅凭文件与 SDK 即可完整解释数据并按触发号、空间坐标（经 `crs_transforms`）、声束号等参数访问所需内容，不依赖 UMS 或业务数据库；不承诺外部 `h5py` 裸翻内部路径，也不维持 HDF5 1.14 独立读取器双实现负担（[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）。

## 2. 设计基线与核心架构决定

<a id="integration-policy"></a>
### 设计维护原则

1. `DATA_SPEC.md` 是唯一权威数据与存储契约，`SDK_CONTRACT.md` 承接首版工程合同，`WIRE_FORMAT.md` 定义磁盘二进制编码，需求与总体理由在本文维护，决定记录一页一事在 `decisions/`。其他文档只引用规则编号，不重述规则（[ADR-0007](decisions/0007-documentation-structure.md)）。
2. 未闭合的事实输入与后置项统一登记于 `DATA_SPEC.md` 的 `D-01`–`D-19` 与 `DECISION_DIRECTIONS.md`，不靠隐含默认偷渡定案。

<a id="baseline-closure"></a>
### 本次定型与减痛重构基线（ADR-0011～0021）

- **业务模型与多区域拼接/复检打通（`ADR-0011～0017`、`0021`）**：确立两层架构、首版单晶/相控阵全波 + 伴生/旁路快照（`wave_and_feature`/`FeatureOnly`/`FMC` 归 M4）、轻量 M:N `Region` + 逻辑拼接组 `ScanGroup`、1..N Scan/多次追加/按层状态来源快照与版本化旁路指针、多目标含可选跨文件 `target_file_uuid` 复检引线，以及强类型最小解码核 + ASTM E2339/**E2663**（含水浸/2D-TCG/PCS）可选物理表 + `crs_transforms`。
- **存储引擎减痛与极简 `push`-only ABI（`ADR-0018～0021`）**：保留 HDF5 容器壳但砍掉按 Scan SWMR 与内嵌 `journal/` 改用外部临时 `.wal`；只读 chunk I/O 移出全局 HDF5 锁；单一 `stored_xxh3` + `O(1)` 打开；帧元合并大块解耦 + `CellCoord` 排序索引；低频 `complete_scan`/`seal`/旁路提交强制 `fsync`；`LIF-02` 强制独立恢复子进程隔离；Core C11 ABI 砍掉 `poll` 与纯内存选择层并明示 `staging_budget`；固化跨平台哨兵锁、`H5dont_atexit`/低 `glibc`/`/MT` 加固并将 Windows + `.NET 4.8` 烟雾闭环前移至 M2。
- **验证状态说明**：目前只有文档契约与 `experiments/m1/` 历史原型；尚无产品 SDK 实现，下一步直接启动极简 `uss.h` 与代码驱动的薄垂直切片。

<a id="core-scope"></a>
### 核心架构决定速查

| 主题域 | 已定架构决定与理由 | 规则与 ADR 入口 |
|---|---|---|
| **两层与首版范围** | Core 与 M4 独立扩展层（选峰、3D 索引/多回波）分离；Core 首版聚焦单晶/PA 全波 + 伴生/旁路快照，`wave_and_feature`/`FeatureOnly`/`FMC` 归 M4 | [BUS-01](DATA_SPEC.md#bus-01)、[RET-01](DATA_SPEC.md#ret-01)、[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)、[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md) |
| **容器、拼接与复检** | 不变 UUID、轻量 M:N `Region`、逻辑拼接组 `ScanGroup`、多目标 `reinspection_targets[]`（含可选跨文件 `target_file_uuid`）与 `continuation_of_file_uuid`；`cancel_empty_scan()` 修复 `N==0` 死锁，封存后不重开追加 | [ID-01](DATA_SPEC.md#id-01)、[SCAN-01/02](DATA_SPEC.md#scan-01)、[LIF-01](DATA_SPEC.md#lif-01)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md) |
| **分模式 Schema 与物理表** | 最小解码核走强类型 C11 结构体（无歧义 `SignalDescriptor`/`POSE_6D`/`crs_transforms`/逐轴编码器有效位/DMA 双阵法则）；ASTM E2339/E2663 & NeXus 可选物理表（水浸/多探头/2D-TCG/PCS）与 `VendorExtension` 走机读 JSON Schema | [REL-01](DATA_SPEC.md#rel-01)、[META-01](DATA_SPEC.md#meta-01)、[WAV-01/02](DATA_SPEC.md#wav-01)、[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md) |
| **统一快照与版本化旁路** | `FileOpen` 态按 Scan 多次追加不可变伴生快照，支持 1..N Scan 整件拼接与按层独立 `status`/`source`；离线派生写独立 Write-Once 旁路容器，Windows 采用不可变版本化文件名 + 原子指针切换避开共享锁冲突 | [SNAP-01](DATA_SPEC.md#snap-01)、[ADR-0014](decisions/0014-configurable-selection-and-snapshot-source.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md) |
| **大块帧元、索引与位图** | 帧级定长元数据合并大块 `frames/meta`（脱离波形 `F_chunk`，取消 `CUSTOM_STRUCT`），`complete_scan()` 写出排序 `frames/cell_index` 实现百 GB `O(log N)` 查回；原始波形位图统一 LSB-first packed bitset | [POS-01/02](DATA_SPEC.md#pos-01)、[PA-01](DATA_SPEC.md#pa-01)、[STA-01](DATA_SPEC.md#sta-01)、[ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md) |
| **减痛物理引擎与耐久恢复** | HDF5 2.x 非 SWMR 写 1.10–1.14（取消 1.14 双实现门禁）；波形 `(F,K,S)` 1–4 MiB + `none/shuffle+zstd/shuffle+lz4` + 单一 `stored_xxh3`；外部临时 `.wal` 增量追加（封存删）；低频 `complete_scan`/`seal`/旁路强制 `fsync`；`LIF-02` 强制独立恢复子进程隔离 | [MAP-01/02](DATA_SPEC.md#map-01)、[WRT-01–03](DATA_SPEC.md#wrt-01)、[LIF-02](DATA_SPEC.md#lif-02)、[ADR-0008](decisions/0008-process-crash-scope.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md) |
| **极简 `push`-only 读与并发** | C11 ABI 砍掉 `poll` 与纯内存选择层（合并分析/Batch 为单一连续 `push` 原语，离散清单留 v0.2）；明示 `staging_budget` 解开两阶段读不可能三角；只读块 I/O 移出 HDF5 全局锁并发 `pread`/`ReadFile`；OS 文件 ID + 哨兵字节跨进程锁 | [CORE-01](DATA_SPEC.md#core-01)、[READ-01–03](DATA_SPEC.md#read-01)、[BUF-01](DATA_SPEC.md#buf-01)、[CAP-01](DATA_SPEC.md#cap-01)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md) |
| **技术栈、跨平台加固与版本** | C++20 + 极简 C11 ABI 静态单库（`H5dont_atexit`/`H5PLset_loading_state(0)`/低 `glibc`/`/MT`）+ `.NET`（`net10.0`/`net48`）首版优先，Windows 烟雾闭环前移至 M2；Python 归 M4；v0.x 快速迭代，`1.0-rc` 起冻结并启用 `abidiff` | [API-01](DATA_SPEC.md#api-01)、[SDK_CONTRACT.md](SDK_CONTRACT.md)、[ADR-0020](decisions/0020-implementation-stack-bindings-and-versioning.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md) |

## 3. 需求基线

编号用于关联 Spec 与验证追踪，不表示相应能力已实现或验收通过。

| 编号 | 已确认需求与产品边界 |
|---|---|
| <a id="r-01"></a>R-01 | 采用中立交付容器（不变文件 UUID、轻量 M:N `Region`、逻辑拼接组 `ScanGroup` 与多 `Scan`，工件与 Run 可选），原始结果 Write-Once 不可覆盖，跨文件复检/续扫留轻量 UUID 引线（联合解析归 `D-19`），混合范围归 `D-13` |
| <a id="r-02"></a>R-02 | 对外提供按扫描类型独立清晰的 Schema（首版单晶、常规 PA 全波，预留 FMC/仅特征/混合）以平衡自描述与读写效率；底层共享同一套物理 I/O 引擎；同一采集单元内长度、dtype、样本表示及采样解释固定 |
| <a id="r-03"></a>R-03 | 采集层归组完整 Frame、波形、位置及关联后提交；SDK 不做时间配准、帧号回绕展开、逐流等待拼装或晚到补写 |
| <a id="r-04"></a>R-04 | Core 原生支持极简 `push` 连续区间读取（含块几何/容量查询与有界 `staging_budget`）、`CellCoord` 排序索引 `O(log N)` 查回及规范子集；纯内存帧内选择留上层；读取不改写原始文件 |
| <a id="r-05"></a>R-05 | 原始波形槽位采用单一 LSB-first packed bitset（写入显式提交完整位图）：有效非零与真实全 0 均无损保真，无效槽位零填充；SDK 管结构与类型校验，不做业务合法性判断 |
| <a id="r-06"></a>R-06 | 同步单 Frame/Batch 写入允许阻塞、无取消；高频 Flush 保障进程崩溃可经外部 `.wal` 恢复并通过 `stored_xxh3` 校验，低频 `complete_scan`/`seal`/旁路提交强制 `fsync`；不负责设备背压 |
| <a id="r-07"></a>R-07 | 实时显示走采集内存；原始文件封存后彻底不可变（Write-Once，支持 `FileOpen` 态按 Scan 多次追加伴生快照）；离线派生快照写版本化 Write-Once 旁路容器 |
| <a id="r-08"></a>R-08 | 未正常关闭的文件通过独立只读恢复子进程原地只读恢复，逐 Scan 报告可验证前缀与失败对象，不复制或改写源文件，不拖垮宿主进程 |
| <a id="r-09"></a>R-09 | 支持超过 100 GB、远超 RAM 的单文件；单 Scan 帧数 N 在 u64 范围，`O(1)` 打开与有界内存，单 Frame 不分块，无分卷与隐含全局 Frame 轴 |
| <a id="r-10"></a>R-10 | 支持无损压缩降低写入带宽与存储体积（内置 `none`/`shuffle+zstd`/`shuffle+lz4`），编码链自解释可识别；CPU 可读是基础，GPU 解压是 M4 可选能力 |
| <a id="r-11"></a>R-11 | 采集设置按 Scan/事件/流组固定保存一次（强类型最小解码核 + ASTM E2339/E2663 可选物理表 + `VendorExtension`），不存逐帧配置历史；定义真实变化时创建新 Scan |
| <a id="r-12"></a>R-12 | 多 Scan 原始结果在容器内独立并存，不隐式融合或替代；支持文件内 M:N `Region`、多区域逻辑拼接组 `ScanGroup` 与多目标复检引线（跨文件联合归 `D-19`） |
| <a id="r-13"></a>R-13 | 仅凭文件与 SDK 即可独立解释已有超声数据（无歧义 `SignalDescriptor`、物理表、`crs_transforms` 刚体变换链、参数化曲面几何及关系），不依赖 UMS 业务数据库 |
| <a id="r-14"></a>R-14 | 进程内 HDF5 元数据全局串行、只读 chunk I/O 锁外并发；同一对象不并发；多进程只读已封存文件；写期间经 OS 文件 ID + 哨兵字节锁拒绝同/跨进程 Reader；首版交付极简 C11 ABI + `.NET`（`net10.0`/`net48`） |
| <a id="r-15"></a>R-15 | 每次读写调用强原子：`push` 在 `staging_budget` 内失败目标逐字节不变；写失败无新增提交、禁原位重试、禁补写未 Flush 尾部；独立报告错误码与提交状态 |
| <a id="r-16"></a>R-16 | 逻辑上支持全波、仅特征与流式混合保留（Core 首版聚焦 `full_wave` + 伴生/旁路快照，其余两种归 M4）；Scan `EndStatus`（含 `CANCELLED_EMPTY`）配合空 `Region` 如实记录局部/故障成果，正常封存拒空壳 |
| <a id="r-17"></a>R-17 | 伴生快照（按 Scan 多次不可变追加）与版本化 Write-Once 旁路容器共用同一模型，支持 1..N Scan 整件拼接与按层独立状态/来源，来源不可篡改且更新避开 Windows 锁冲突（[SNAP-01](DATA_SPEC.md#snap-01)） |
| <a id="r-18"></a>R-18 | Core 原生按连续触发区间与 `CellCoord` 排序索引（`O(log N)`）提供 `0~N` 来源访问；3D 旁路空间索引与可插拔多回波代表选择归 M4 独立扩展层（`D-17`） |
| <a id="r-19"></a>R-19 | 独立可选扩展层（M4）提供文件输入、明确窗口内的选峰基础取值（幅值与前沿位置/时间+幅值），区域保形逐点状态（`D-18`）；不做物理量转换、滤波包络或复杂分析 |
| <a id="r-20"></a>R-20 | 承担以文件为载体的跨系统数据交付（UMS、其他扫描系统创建、外部系统完整读取）；执行期进程内分发与上位机内存池归调用方 |

## 4. 首版不包含的范围

- **流程与外部系统职责**：UI/保存交互、Workflow、设备控制、采集归组/重连、扫描复现、执行期分发与内存池、标注与缺陷分析成果、激光点云、复杂处理（包络/滤波/成像/同步跟随门/跨波形跟踪）及额外导出（图片/CSV/打包）。
- **明确拒绝或排除的存储与 ABI 行为**：
  - 封存或干净关闭后重开追加原始波形（`D-15` 已关闭）；
  - 正常完成 0 帧 Scan（需显式 `cancel_empty_scan`）、正常封存 0-Scan 空壳、写失败态原位重试或补写未 Flush 尾部；
  - 对已封存原始文件或旁路文件原地修改/热替换；
  - Core C11 ABI 中的 `poll` 借用视图、纯内存帧内选择层、`CUSTOM_STRUCT`、按 Scan SWMR 与 HDF5 1.14 独立读取器双实现门禁；
  - 在线读取增长中的未封存文件、多写者、多活动 Scan 交错追加、分卷、隐式拼接、内置 `deflate` 与 `f64`/复数波形样本，以及外部 `h5py` 裸翻内部路径承诺。
- **预留或后置至 v0.2 / M4+**：离散帧清单（v0.2）；`wave_and_feature`（流式硬件特征与选择性留波）、`FeatureOnly`、`FMC`、官方 Python 绑定、独立扩展层（`D-17`/`D-18`）、GPU 解压（`D-06`）、混合扫描与多独立运动探头（`D-13`）、部分/跨组矩阵（`D-14`）、多文件联合解析（`D-19`）。

## 5. 设计定型视图与文档唯一职责

### 定型状态检查

| 板块 | 当前状态 | 下一步入口 |
|---|---|---|
| 1. 业务模型、多区域拼接/复检与快照 | **已定型并修复 P0（`ADR-0015～0017`、`0021`）** | 随 M2 薄切片用首批实机样本核对可选物理表（`D-09`） |
| 2. 减痛物理引擎（非 SWMR + 外部 `.wal` + 大块帧元） | **已定型（`ADR-0021` + `WIRE_FORMAT.md r2`）** | M2 薄切片实测 EA `>=20,000` 块 SIGKILL 与隔离恢复子进程（`D-05`） |
| 3. 极简 `push`-only C11 ABI 与跨平台加固 | **已定型（`ADR-0010`/`0020`/`0021`）** | 紧接起草极简 `uss.h` 并跑通 Linux + Windows MSVC/`.NET 4.8` 烟雾闭环 |
| 4. 扩展层、流式特征与后置项 | **明确排期至 v0.2 / M4+（不阻塞 Core）** | 见 [DECISION_DIRECTIONS.md](DECISION_DIRECTIONS.md) |

### 仓库文档唯一职责（高内聚分工）

| 文档 | 唯一职责 |
|---|---|
| `DESIGN.md`（本文） | 产品全景、两层边界、需求基线（`R-01`–`R-20`）、核心决定总览与排除范围 |
| `DATA_SPEC.md` | 唯一权威数据与存储契约、逻辑模型、写入保护语义、不变量（`U-01`–`U-16`）与 `D-01`–`D-19` 状态总表 |
| `SDK_CONTRACT.md` | Core 首版工程合同：交付矩阵、编码 Profile、极简 `push`-only C11 ABI 与状态机、锁与跨平台加固、`.NET` 绑定与版本门禁 |
| `WIRE_FORMAT.md` | M2 HDF5 Wire Format 1.0 规范草案（`1.0-draft r2`）：磁盘二进制布局、外部 `.wal`、大块 `frames/meta`、`cell_index` 与样例 |
| `DECISION_DIRECTIONS.md` | 仅列剩余待补实机事实输入、M2 薄切片任务与 v0.2/M4 后置项 |
| `decisions/` | 已采纳决定的背景、理由、证据与后果（`ADR-0001`–`0021`，一页一事） |
| `SPEC_TEST_PLAN.md` | 访问场景分工、TFM 边界、`H/P/F/W` 独立数值期望、`UC`/`T` 追踪、里程碑与 Core 门禁 |
| `SCENARIO_AUDIT.md` | UMS 业务/架构事实留档、设备/算法审计模板与历史微基准证据局限 |
