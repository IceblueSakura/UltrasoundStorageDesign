# 超声数据 SDK：需求、两层架构与设计收敛视图

状态：已依据 [ADR-0001～ADR-0020](decisions/README.md) 完成 Core 首版设计与工程定型（Spec `0.3-draft`）；当前已具备进入 M2 格式/ABI 细化与工程原型的条件，不修改或重跑既往实验。

本文维护产品定位、需求基线（`R-01`–`R-20`）、核心架构决定与审阅确认视图。数据与存储契约唯一定位于 [DATA_SPEC.md](DATA_SPEC.md)，首版工程合同与 C11 ABI/绑定规格位于 [SDK_CONTRACT.md](SDK_CONTRACT.md)，已采纳决定背景在 [ADR 目录](decisions/README.md)，仅剩的待补事实与 M2 清单集中在 [DECISION_DIRECTIONS.md](DECISION_DIRECTIONS.md)。

## 1. 产品全景与两层架构

SDK 是包含权威 schema 与规范化读写能力的单一超声数据存储产品，独立维护并开源。它面向 **UMS 保存与重开**、**其他扫描系统创建扫描数据**、**其他集成与外部分析完整读取**三类使用者，承担以文件为载体的跨系统数据交付（[ADR-0015](decisions/0015-cross-system-data-delivery.md)、[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)）。

```text
+-------------------------------------------------------------------------+
| SDK Core（C++20 核心 + 纯 C11 ABI 静态自包含单库；首版绑定 .NET 10 / 4.8）|
|  · 中立交付容器：不变文件 UUID、轻量 M:N Region、多 Scan/EndStatus       |
|  · 分模式独立 Schema：首版单晶 / 相控阵（预留 FMC / 仅特征）             |
|  · 自包含解释：最小解码必填核 + DICONDE/NeXus 可选物理表 + VendorExtension|
|  · 原生高效寻址：触发号 / 声束 / 通道 / 样本窗口 + 可选离散 CellCoord    |
|  · 物理 I/O 引擎：HDF5 2.x 写 1.10–1.14、可配置 (F,K,S) 分块、           |
|                  none/shuffle+zstd/shuffle+lz4、XXH3-64、MAP-02+SWMR     |
|  · 读写接口：连续+离散按块合并 Batch、poll/push 两阶段读、块几何容量查询 |
|  · Write-Once 生命周期：采集写原始数据 → 可选写1次伴生快照 → 永久只读    |
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

[统一快照模型与 Write-Once 旁路分离]
  原始采集文件（Acquisition）：顺序写 Scan (1..K, N>=1) ─→ [可选] 封存前写 1 次伴生快照 ─→ 封存只读
                                                                                              │
  离线派生快照（DerivedSnapshot）：独立 Write-Once 旁路容器（强绑定 UUID+ScanID，临时文件+原子 rename）

[明确排除（留待调用方/UMS）]
  · UI / Workflow / 设备控制 / 扫描复现 / 执行期进程内分发与上位机内存池（Batch-of-SoA 由调用方管理）
  · 激光点云 / 包络滤波或成像引擎 / 标注与缺陷分析成果 / 额外导出（图片/CSV/打包）
```

**自描述边界**：仅凭文件与 SDK 即可完整解释数据并按触发号、空间坐标、声束号等参数访问，不依赖 UMS 或业务数据库；不再承诺外部第三方工具（如 `h5py`）不经 SDK 裸翻内部路径，物理布局彻底服务于读写效率（[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)）。

## 2. 设计基线与核心架构决定

<a id="integration-policy"></a>
### 设计维护原则

1. `DATA_SPEC.md` 是唯一权威数据与存储契约，`SDK_CONTRACT.md` 承接首版工程合同与 ABI/绑定规格，需求与总体理由在本文维护，决定记录一页一事在 `decisions/`。其他文档只引用规则编号，不重述规则或维护第二套契约（[ADR-0007](decisions/0007-documentation-structure.md)）。
2. 逻辑语义与 M2 精确 wire 编码/C11 签名分开；不因历史 M1 原型写法提前冻结生产格式。
3. 未闭合的事实输入与后置项统一登记于 `DATA_SPEC.md` 的 `D-01`–`D-19` 与 `DECISION_DIRECTIONS.md`，不得通过默认实现或测试断言偷偷定案。

<a id="baseline-closure"></a>
### 本次定型基线（ADR-0011～0020）

- **业务模型与首版范围收口（`ADR-0011～0017`）**：确立两层架构、首版聚焦单晶 + 相控阵 + 伴生/旁路快照（预留仅特征/FMC）、轻量 M:N `Region`、统一快照 + Write-Once 旁路容器、最小解码核 + DICONDE/NeXus 可选物理表 + 参数化曲面几何，以及可配置 `(F_chunk, K_chunk, S)` 物理分块。
- **物理引擎、编码与工程栈定型（`ADR-0018～0020`）**：正式采用 `MAP-02` + 按 Scan SWMR、严格拒绝正常空对象与写失败态原位重试、`XXH3-64`、`{i8..u32, f32}`、`none/shuffle+zstd/shuffle+lz4`、LSB-first packed bitset、连续+离散按块合并 Batch、C++20 核心 + 纯 C11 ABI 静态自包含单库、首版 `.NET`（`net10.0`/`net48`）优先（Python 延后至 M4）及三套版本解耦与 `1.0` `abidiff` 门禁。
- **验证状态说明**：目前只有文档契约与 `experiments/m1/` 的 test-only 机制原型（仅验证了单一 PA 流组部分机制）；尚无产品 SDK 实现或全量合格证据。

<a id="core-scope"></a>
### 核心架构决定速查

| 主题域 | 已定架构决定与理由 | 规则与 ADR 入口 |
|---|---|---|
| **两层与首版范围** | SDK 分为 Core 与独立可选扩展层（M4：选峰、3D 索引/多回波）；Core 首版聚焦单晶 + 相控阵 + 伴生/旁路快照，预留 `FeatureOnly`/`FMC`；面向 UMS 与外部系统跨系统交付 | [BUS-01](DATA_SPEC.md#bus-01)、[MEAS-01](DATA_SPEC.md#meas-01)、[ADR-0015](decisions/0015-cross-system-data-delivery.md)、[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)、[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md) |
| **中立容器、Region 与 Scan** | 不变文件 UUID；轻量 M:N `Region` 实体（可表未执行空区域）；Scan 显式 `EndStatus`；段内暂停同 Scan，正常完成/封存拒空对象，封存/关闭不重开追加（`D-15` 关闭） | [ID-01](DATA_SPEC.md#id-01)、[SCAN-01/02](DATA_SPEC.md#scan-01)、[LIF-01](DATA_SPEC.md#lif-01)、[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)、[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)、[ADR-0018](decisions/0018-storage-engine-swmr-and-strict-lifecycle.md) |
| **分模式 Schema 与参数分层** | 按扫描类型独立清晰 Schema；“最小解码必填核（`SignalDescriptor`/采样轴/映射）+ DICONDE/NeXus 强类型可选物理表 + 参数化曲面几何 + `VendorExtension`”；首发 dtype `{i8..u32, f32}` 按位保真 | [REL-01](DATA_SPEC.md#rel-01)、[META-01](DATA_SPEC.md#meta-01)、[WAV-01/02](DATA_SPEC.md#wav-01)、[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)、[ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md) |
| **统一快照与 Write-Once 旁路** | 原始文件封存前可选写 1 次伴生 C 扫快照后永久不可变；离线派生快照共用同一逻辑模型，写入独立 Write-Once 旁路容器（强绑定 UUID+ScanID，临时文件 + 原子 `rename` 替换） | [SNAP-01](DATA_SPEC.md#snap-01)、[ADR-0014](decisions/0014-configurable-selection-and-snapshot-source.md)、[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)、[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md) |
| **位置、附加记录与位图** | 固定列式 Schema：无位置合法、启用位置带显式 `pos_valid` 与同步等级、可选 `CellCoord[Frame]`（`int32[1..3]` + 无归属位）、逐列 `required`/`nullable` 附加记录；原始波形位图统一 LSB-first packed bitset + Writer/Scan 级严格模式 | [POS-01/02](DATA_SPEC.md#pos-01)、[PA-01](DATA_SPEC.md#pa-01)、[STA-01](DATA_SPEC.md#sta-01)、[ADR-0003](decisions/0003-explicit-validity-bitmap.md)、[ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md) |
| **物理引擎、编码与耐久恢复** | HDF5 2.x 写 1.10–1.14；可配置 `(F_chunk, K_chunk, S)` 分块（默认 1–4 MiB）；内置 `none`/`shuffle+zstd`/`shuffle+lz4`；`XXH3-64` 逐块校验；正式选定 `MAP-02` + 按 Scan SWMR（仅保进程崩溃、不要求 `fsync`）；写失败禁重试；双槽提交全毁不可恢复；`LIF-02` 原地只读不改源文件 | [MAP-01/02](DATA_SPEC.md#map-01)、[WRT-01–03](DATA_SPEC.md#wrt-01)、[IO-01](DATA_SPEC.md#io-01)、[LIF-02](DATA_SPEC.md#lif-02)、[CMP-01](DATA_SPEC.md#cmp-01)、[ADR-0002](decisions/0002-durability-and-failure.md)、[ADR-0005](decisions/0005-file-format-range.md)、[ADR-0008](decisions/0008-process-crash-scope.md)、[ADR-0018](decisions/0018-storage-engine-swmr-and-strict-lifecycle.md)、[ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md) |
| **读取、Batch 与内存池** | 连续 `(start, count)` + 离散帧清单（按块合并解码）双 Batch；跨组每组独立缓冲；局部越界与空选择整体拒绝；`poll` 借用 + `push` 两阶段读；提供不失效 `poll` 的块几何与容量查询适配 UMS `Batch-of-SoA`；进程内 HDF5 全局串行、多进程只读已封存文件、写期间自检拒 Reader | [CORE-01](DATA_SPEC.md#core-01)、[READ-01–03](DATA_SPEC.md#read-01)、[BUF-01](DATA_SPEC.md#buf-01)、[CAP-01](DATA_SPEC.md#cap-01)、[ADR-0004](decisions/0004-concurrency-and-borrow-scope.md)、[ADR-0006](decisions/0006-core-io-and-selection-layer.md)、[ADR-0009](decisions/0009-review-contract-clarifications.md)、[ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md) |
| **技术栈、绑定与版本门禁** | C++20 实现 + 纯 C11 ABI 静态打包 HDF5 2.x/zstd/lz4 单库分发；首版（M3）仅交付 C ABI + `.NET`（`net10.0`/`net48`，`SafeHandle` + >2 GiB 非托管缓冲 + 受检 `poll`），Python 延后至 M4；Format/Schema/SemVer 三轴解耦，`1.0` 冻结并启用 SONAME/符号版本/`abidiff` | [API-01](DATA_SPEC.md#api-01)、[SDK_CONTRACT.md](SDK_CONTRACT.md)、[ADR-0010](decisions/0010-public-api-stability.md)、[ADR-0020](decisions/0020-implementation-stack-bindings-and-versioning.md) |

## 3. 需求基线

编号用于关联 Spec 与验证追踪，不表示相应能力已实现或验收通过。

| 编号 | 已确认需求与产品边界 |
|---|---|
| <a id="r-01"></a>R-01 | 采用中立交付容器（不变文件 UUID、轻量 M:N `Region` 与多 `Scan`，工件与 Run 为可选元数据），原始结果 Write-Once 不可覆盖，跨文件复检归 `D-19`，混合范围归 `D-13` |
| <a id="r-02"></a>R-02 | 对外提供按扫描类型独立清晰的 Schema（首版单晶、常规 PA，预留 FMC 与仅特征）以平衡自描述与读写效率；底层共享同一套物理 I/O 引擎；同一采集单元内长度、dtype、样本表示及采样解释固定 |
| <a id="r-03"></a>R-03 | 采集层归组完整 Frame、波形、位置及关联后提交；SDK 不做时间配准、帧号回绕展开、逐流等待拼装或晚到补写 |
| <a id="r-04"></a>R-04 | Core 原生支持连续与离散 Batch/分析读取（含 `poll` 借用与 `push` 两阶段复制）及规范子集，不预定任意坐标搜索；帧内选择为纯选择层；读取不改写原始文件 |
| <a id="r-05"></a>R-05 | 原始波形槽位采用单一 LSB-first packed bitset（写入显式提交完整位图，存储初值为无效）：有效非零与真实全 0 均无损保真，无效槽位零填充；SDK 管结构与类型校验，不做业务合法性判断 |
| <a id="r-06"></a>R-06 | 同步单 Frame/Batch 写入允许阻塞、无取消；普通写入不立即落盘，显式 Flush 成功后数据在进程崩溃后可恢复并通过 `XXH3-64` 校验（不保断电/OS 崩溃）；不负责设备背压或端到端采集不丢数据 |
| <a id="r-07"></a>R-07 | 实时显示走采集内存；原始文件封存后彻底不可变（Write-Once，支持封存前写一次伴生快照）；离线派生快照写独立 Write-Once 旁路容器或另存新目标 |
| <a id="r-08"></a>R-08 | 未正常关闭（含封存前崩溃）的文件支持显式尽力原地只读恢复，逐 Scan 报告可验证前缀与失败对象，不复制或改写源文件 |
| <a id="r-09"></a>R-09 | 支持超过 100 GB、远超 RAM 的单文件；单 Scan 帧数 N 在 u64 范围，有界内存与单 Frame 不分块，无分卷与隐含全局 Frame 轴 |
| <a id="r-10"></a>R-10 | 支持无损压缩降低写入带宽与存储体积（内置 `none`/`shuffle+zstd`/`shuffle+lz4`），编码链与参数必须自解释可识别；CPU 可读是基础，GPU 解压是 M4 可选能力 |
| <a id="r-11"></a>R-11 | 采集设置按 Scan/事件/流组固定保存一次（最小解码核 + DICONDE/NeXus 可选物理表 + `VendorExtension`），不存逐帧配置历史；定义真实变化时创建新 Scan |
| <a id="r-12"></a>R-12 | 多 Scan 原始结果在容器内独立并存，不自动拼接、融合或替代；支持文件内 M:N `Region` 关联与复检来源引用（跨文件归 `D-19`） |
| <a id="r-13"></a>R-13 | 仅凭文件与 SDK 即可独立解释已有超声数据（模式参数、采样含义、参数化曲面几何及关系），不依赖 UMS 业务数据库，也不以透传无约定字典代替解释责任 |
| <a id="r-14"></a>R-14 | 进程内 HDF5 调用全局串行化；同一对象不并发调用；多 Reader 借用独立，已封存文件可多进程只读；单写者期间 SDK 自检拒绝同/跨进程 Reader；首版交付 C ABI + `.NET`（`net10.0`/`net48`） |
| <a id="r-15"></a>R-15 | 每次读写调用强原子：`push` 失败目标不变；`poll` 失败不发布新视图且旧借用到期；写失败无新增提交、历史不变且 Writer 进入失败态禁重试；独立报告错误码与提交状态 |
| <a id="r-16"></a>R-16 | 全波、仅特征（预留独立不可变 Schema）与混合保留均合法；有意未保留、缺测、无效、有效零值与 Scan `EndStatus` 分别表达，配合空 `Region` 如实记录局部/故障成果（正常封存拒空 Scan/空文件） |
| <a id="r-17"></a>R-17 | 采集期伴生快照（封存前 Write-Once 1 次）与离线 Write-Once 旁路容器共用同一模型，确保来源不可篡改与替换原子保旧（[SNAP-01](DATA_SPEC.md#snap-01)）；不纳入标注或缺陷成果 |
| <a id="r-18"></a>R-18 | Core 原生按触发号/声束/通道与可选离散 `CellCoord` 提供 `0~N` 完整来源访问；3D 旁路空间索引与可插拔多回波代表选择归 M4 独立扩展层（`D-17`） |
| <a id="r-19"></a>R-19 | 独立可选扩展层（M4）提供文件输入、明确窗口内的选峰基础取值（幅值与前沿位置/时间+幅值），区域保形逐点状态（`D-18`）；不做物理量转换、滤波包络或复杂分析 |
| <a id="r-20"></a>R-20 | 承担以文件为载体的跨系统数据交付（UMS、其他扫描系统创建、外部系统完整读取）；执行期进程内分发与上位机内存池归调用方 |

## 4. 首版不包含的范围

- **流程与外部系统职责**：UI/保存交互、Workflow、设备控制、采集归组/重连、扫描复现、执行期分发与内存池、标注与缺陷分析成果、激光点云、复杂处理（包络/滤波/成像/同步跟随门/跨波形跟踪）及额外导出（图片/CSV/打包）。
- **明确拒绝或排除的存储行为**：
  - 封存或干净关闭后重开追加原始波形（`D-15` 已关闭）；
  - 正常完成 0 帧 Scan、正常封存无 Scan 空文件、写失败态下原位重试追加（`ADR-0018`）；
  - 对已封存原始文件或旁路文件进行原地修改/热替换；
  - 在线读取增长中的未封存文件、多写者、多个活动 Scan 交错追加、跨 Scan 定义去重、分卷、自动拼接/重扫融合；
  - 单 Frame 内分块交付、异步可取消写入、自动修复或原地截断损坏文件、断电与操作系统崩溃持久化承诺；
  - 外部工具不经 SDK 裸翻 HDF5 内部路径的兼容性承诺，以及内置 `deflate` 编解码与 `f64`/复数样本。
- **预留或后置至 M4+**：`FeatureOnly` 与 `FMC` 模式细节、官方 Python 绑定、独立扩展层（`D-17`/`D-18`）、GPU 解压（`D-06`）、混合扫描与多独立运动探头（`D-13`）、部分/跨组矩阵（`D-14`）、多文件与跨文件复检（`D-19`）。

## 5. 设计定型视图与文档唯一职责

### 定型状态检查

| 板块 | 当前状态 | 下一步入口 |
|---|---|---|
| 1. 两层边界、容器与首版业务模型 | **已定型（`ADR-0015～0017`）** | 进入 M2 补齐真实设备字段清单（`D-09`）与 wire 编码（`D-11`/`D-16`） |
| 2. 物理引擎、故障边界与数据编码 | **已定型（`ADR-0018～0019`）** | M2 补多级块索引 SIGKILL 实验（`D-05`）与精确 HDF5 wire 规范（`D-07`） |
| 3. C11 ABI、技术栈、`.NET` 与版本门禁 | **已定型（`ADR-0010`/`0020`）** | M2 起草 `uss.h` 签名/错误码/状态表（`D-10`）与补齐设备规模预算（`D-02`/`D-03`） |
| 4. 扩展层、Python 绑定与后置项 | **明确排期至 M4+（不阻塞 Core）** | 见 [DECISION_DIRECTIONS.md](DECISION_DIRECTIONS.md#3-独立扩展层与明确后置项归-m4-或后续不阻塞-core-m2m3) |

### 仓库文档唯一职责（高内聚分工）

| 文档 | 唯一职责 |
|---|---|
| `DESIGN.md`（本文） | 产品全景、两层边界、需求基线（`R-01`–`R-20`）、核心决定总览与排除范围 |
| `DATA_SPEC.md` | 唯一权威数据与存储契约、逻辑模型、`MAP-02`+SWMR 语义、不变量（`U-01`–`U-16`）与 `D-01`–`D-19` 状态总表 |
| `SDK_CONTRACT.md` | Core 首版工程合同：交付矩阵、编码 Profile、C11 ABI 与状态机、Batch/缓冲接口、C++20 静态打包、`.NET` 绑定与 `1.0` 版本门禁 |
| `DECISION_DIRECTIONS.md` | 仅列剩余待补事实输入、M2 细化任务与 M4/后置项 |
| `decisions/` | 已采纳决定的背景、理由、证据与后果（`ADR-0001`–`0020`，一页一事） |
| `SPEC_TEST_PLAN.md` | 访问场景分工、TFM 边界、`H/P/F/W` 独立数值期望、`UC`/`T` 追踪、里程碑与 Core 门禁 |
| `SCENARIO_AUDIT.md` | UMS 业务/架构事实留档、设备/算法审计模板与历史微基准证据局限 |
