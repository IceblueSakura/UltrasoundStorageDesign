# 超声采集数据 Spec 0.3-draft

状态：`0.3-draft`，已依据 [ADR-0001～ADR-0020](decisions/README.md) 完成 Core 首版设计与工程选型定型；本文是数据语义、物理存储架构、不变量与 `D-01`–`D-19` 状态的唯一规范来源。公开 C11 ABI、首版编码 Profile、技术栈、`.NET` 绑定与版本门禁配套定位于 [SDK_CONTRACT.md](SDK_CONTRACT.md)；不修改或重跑既往实验与 benchmark。

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

- **两层模型与首版聚焦**：本规范确立 **SDK Core + 独立可选扩展层**两层架构（[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)）。Core 首版（M2 冻结 / M3 交付）聚焦 **单晶（`SingleProbe`）+ 相控阵（`PhasedArray`）+ 伴生/旁路 C 扫快照**，`FeatureOnly`（仅特征）与 `FMC` 在 Schema 类型枚举中保留预留口，本轮不展开字段细节（[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)）；独立可选扩展层仅消费 Core 只读 API，不进入 Core 文件格式与写入路径。
- **格式兼容性与自描述分工**：底层使用 HDF5 2.x 库写出 HDF5 1.10–1.14 可读的二进制格式（[ADR-0005](decisions/0005-file-format-range.md)）。自描述指“仅凭文件与 SDK 即可完整解释并按触发号、空间坐标、声束号等参数访问，不依赖 UMS 或业务数据库”；不再承诺外部工具（如 `h5py`）不经 SDK 裸翻内部路径，物理布局彻底服务于读写效率（[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)）。
- **版本与历史证据边界**：`0.3-draft` 为文档状态标签，以 Git 提交区分修订；文件格式版本、模式 Schema 版本与 SDK SemVer 彻底解耦，`0.x` 允许演进，`1.0` 起冻结（[ADR-0020](decisions/0020-implementation-stack-bindings-and-versioning.md)、[SDK_CONTRACT.md](SDK_CONTRACT.md#versioning)）。`experiments/m1/` 为 test-only 机制原型，仅用于 M1 原适用范围取证，不能反向定义产品格式或替代新增业务验收。在 M2 精确 wire 编码与独立读取闭合前，不得宣称生产格式符合性。

<a id="core-01"></a>
### CORE-01：两层架构边界与物理 I/O Core〔确定〕

- **Core 与扩展层职责**：Core 负责中立交付容器外壳、分扫描类型独立 Schema、Write-Once 封存只读（含封存前可选写一次伴生 C 扫快照）及 Write-Once 旁路派生容器、触发序号/声束/通道/样本窗口与可选离散单元列 `CellCoord[Frame]` 寻址，以及共享物理 I/O 引擎；选峰基础取值（[MEAS-01](#meas-01)）与 3D 旁路空间索引/多回波代表选择（[ACCESS-01](#access-01)）归独立可选扩展层。
- **原始波形 Core I/O 与纯选择层（[ADR-0006](decisions/0006-core-io-and-selection-layer.md)、[ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md)）**：原始波形路径提供同步单 Frame 与 Frame 批次写入。Core I/O 按一个 Scan、连续区间或离散帧清单（B≥1）及一个或多个流组交付稠密样本、有效性位图、帧位置与帧级附加记录，提供“随元信息返回的分析读取”和“Batch 读取”两种交付方式，各自均可走 `poll` 或 `push`；帧内流/声束/Tx/Rx/样本选择及单 A-Scan 提取是作用于 Core I/O 结果的纯函数，不做文件 I/O，不跨 Scan 自动拼接。
- **并发与锁边界（[ADR-0004](decisions/0004-concurrency-and-borrow-scope.md)、[ADR-0009](decisions/0009-review-contract-clarifications.md)）**：SDK 在进程内对全部 HDF5 调用全局串行化（编解码与 `XXH3-64` 可在锁外并行）；同一 Reader 或 Writer 对象不得并发调用。一个进程可持有多个 Reader，各自 `poll` 借用独立；同一文件同一时刻仅允许一个 Writer，且写入期间不得同时被同进程或跨进程 Reader 打开（SDK 必须主动检测并拒绝，不得只依赖可被环境变量禁用的 HDF5 文件锁）。已封存文件可被多进程同时只读。写入同步消费调用者输入、无写入取消、普通写入不立即落盘。

Core 不负责设备协议解码、帧号回绕展开、时间配准、位置插值或业务字节序转换；平台、实现语言与绑定范围见 [SDK_CONTRACT.md](SDK_CONTRACT.md)。

<a id="api-01"></a>
### API-01：公开接口的稳定边界〔原则与策略已定，签名待 M2〕

原生库唯一稳定边界为 **纯 C11 ABI**（不透明句柄、64 位长度、指针＋字节长显式缓冲、大小/版本开头的可扩展参数结构体、未识别 `flags` 报错、稳定错误码与 `COMMITTED / NOT_COMMITTED / UNKNOWN` 提交状态分离），不泄漏 HDF5 或 C++ 类型/异常（[ADR-0010](decisions/0010-public-api-stability.md)）。C++20 实现、静态自包含单库分发、首版 `.NET`（`net10.0`/`net48`）绑定、版本解耦与 `1.0` `abidiff` 门禁详见 [SDK_CONTRACT.md](SDK_CONTRACT.md)（[ADR-0020](decisions/0020-implementation-stack-bindings-and-versioning.md)）。

<a id="bus-01"></a>
### BUS-01：超声专用产品边界〔确定〕

SDK 是包含权威 schema 与规范读写能力的单一超声数据存储产品，独立维护并开源：

- **三类使用者与跨系统交付（[ADR-0015](decisions/0015-cross-system-data-delivery.md)）**：面向 **UMS 保存与重开**、**其他扫描系统创建扫描数据**、**其他系统集成与外部分析完整读取**；读写合同与调用方的 Run、工件、Workflow 或业务数据库解耦（工件与 Run 为可选元数据）。仅凭文件与 SDK 即可解释与访问文件中的全部超声内容（原始波形、必要解释、位置与状态、数据关系、伴生与旁路快照）。
- **单写与不可变**：保持单写者，不支持采集中读取增长文件；原始文件与旁路派生文件封存后均彻底不可变（Write-Once，[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)、[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)）。
- **明确排除**：执行期进程内分发（向计算/保存/显示广播）与上位机内存池（`Batch-of-SoA`）归调用方；UI/Workflow、保存按钮/弹窗、任务准入/合格判据、设备控制、扫描复现、包络/滤波/成像与复杂闸门分析、激光点云、标注与缺陷成果（归 UMS）、额外导出（图片/CSV/打包）均不在范围。

<a id="ret-01"></a>
### RET-01：保留内容、状态与部分成果〔确定〕

- **三种保留模式**：全波、仅特征、波形与特征混合保留均合法。仅特征采集保留独立不可变 Schema 类型（`FeatureOnly`，首版留预留口），不虚构波形、Frame 或波形有效性位图，封存后不可被离线重算覆盖（硬件直出采集特征同样属于不可覆盖原始记录）；来源关联不要求来源波形仍被保留，缺少输入时明确表达依赖该输入的能力不可用。
- **状态分离与部分成果**：有意未保留、应有但缺失、实际无效、有效零值须分别表达，不得全压进 [STA-01](#sta-01) 单一波形位。`Scan` 显式记录结束状态（`正常完成 / 主动提前结束 / 故障中止及原因`），配合文件内已声明未采集的空 `Region` 实体共同表达部分成果与缺口（[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)）。正常封存须满足非空对象约束（[LIF-01](#lif-01)、[ADR-0018](decisions/0018-storage-engine-swmr-and-strict-lifecycle.md)）。保存成功不证明扫描完整或检测合格；SDK 不自动补齐、推算或伪造数据。

<a id="rel-01"></a>
### REL-01：必要关系与自包含解释〔模型已定，字段名待 M2〕

- **区域与复检关系（[ADR-0013](decisions/0013-region-relations-and-subset-scope.md)、[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)、[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)）**：`Region` 为文件内轻量独立实体（ID、可读名称、可选包围盒/参考系标识与扩展，不内置 CAD/多边形几何计算），与 `Scan` 保持 **M:N 引用**（单 Scan 可关联 `0..N` 个目标 Region，多 Scan 可共享同一 Region；未采集区域可合法留空）。文件内复检由新 `Scan` 可选指向原 `ScanID`/`RegionID`；跨文件复检整体归 `D-19`（定案前由调用方自行持有）；Run 到 Scan 映射留在调用方。新旧扫描保留独立身份，不因关系存在而自动融合或替代。
- **自包含模式解释与曲面几何（[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)）**：单晶与相控阵等采用**按扫描类型独立清晰的 Schema**（不靠 shape 猜测，不依赖无约定字典或本地驱动函数名），实行 **“最小解码必填核 + 强类型标准可选物理表 + `VendorExtension`”** 分层：仅强制解码与映射必需字段（`SignalDescriptor`、采样轴、通道/探头标识与 PA 阵元/聚焦法则映射），探头频率/增益/声速/楔块等参照 ASTM DICONDE（E2339/E2738）与 NeXus 核对清单定义为强类型可选字段；曲面采用几何仅保存解释已有数据必需的轻量参数化描述（平面/柱面/球面等参数或外部参考曲面标识＋坐标系/姿态/法向），不嵌点云或三角网格。

<a id="snap-01"></a>
### SNAP-01：Write-Once 伴生快照与旁路派生容器〔模型已定，wire 编码待 M2〕

- **原始文件 Write-Once 彻底不可变（[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)）**：SDK Core 支持在**原始文件封存前 Write-Once 写入一次**采集期伴生 C 扫快照（加速重开浏览，带参数与来源）。封存后严禁重开原始文件进行原地修改或热替换；仅特征采集文件同样不可被离线重算覆盖。
- **统一快照模型与 Write-Once 旁路派生容器（[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)）**：采集期伴生快照与封存后离线派生快照共用同一逻辑模型（规则 2D 栅格或稀疏点表 + 特征数值层 + 逐点状态 + 实际来源 `(ScanID, FrameIdx, Stream/BeamID)` + 实际采用参数）。离线重算的新增/替换派生快照一律写入本 SDK 管理的独立 **Write-Once 旁路派生容器**（`file_role = DerivedSnapshot`，头部强绑定原始文件的 `FileInstanceUUID` 与 `ScanID`）或另存新目标；覆盖替换通过写临时文件 + 原子 `rename` 保证写失败时既有可用成果完好，绝不改写原始文件。
- **来源不可篡改与参数区分（[ADR-0014](decisions/0014-configurable-selection-and-snapshot-source.md)）**：已保存快照须追溯实际关联的来源；多回波代表选择策略变化时，不得反向重选历史快照来源；来源波形未保留时明确提示不可用，不以同位置另一条波形顶替。区分采集采用参数、分析参数与快照实际采用参数；在线设置曾变更且无历史时不得用最后一组冒充全部分数。

<a id="access-01"></a>
### ACCESS-01：两层寻址、底层来源与扩展层多回波选择〔边界已定，扩展层后置〕

- **五类重点访问场景（[ADR-0013](decisions/0013-region-relations-and-subset-scope.md)）**：浏览已保存 C 扫快照、C 扫选点取 A 波形、区域批量读波形/取值、按 B/D/S 等布局批量读取、分批遍历整次扫描。物理分块模型按 [ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md) 支持可配置 `(F_chunk, K_chunk, S)` 兼顾五类访问，离散帧清单合并解码直接加速 D 扫与 `CellCoord` 查回（[ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md)）。
- **两层寻址分工（[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)）**：
  - **SDK Core 原生寻址**：按触发序号、声束/通道与样本窗口以及可选的离散单元整型列 `CellCoord[Frame]`（无规则布局时省略，不做浮点分箱）交付选定位置实际关联并保留的全部 `0～N` 条原始波形、有效性及来源；`0` 条须与 `RET-01` 内容状态对应。
  - **独立可选扩展层（3D 索引与多回波选择，`D-17`，归 M4）**：仅消费 Core 只读 API，基于原始 3D 坐标按需构建独立旁路空间索引，按 `(x, y, z)` 查出 `0~N` 条候选并执行统一可插拔代表选择策略；相同数据/策略/条件下结果一致，不跨越扫描/声束/声路边界，无有效候选时不以无效波形兜底，不修改原始数据与伴生快照来源。
- **规范数据子集**：Core 支持按选定 `Scan`、基于离散单元或布局的空间区域、通道/声束/收发组合、波形样本窗口提取规范子集，保留必要解释与样本位置来源；不附带图片/CSV 导出或打包。

<a id="meas-01"></a>
### MEAS-01：独立选峰扩展的基础窗口取值〔已移出 Core 归 M4 扩展层〕

明确窗口内的基础幅值与位置/时间取值（如峰峰值、前沿取值）**已移出 SDK Core，归属独立可选扩展层**（只消费 Core 只读 API，不进入 Core 文件格式与写入路径，`D-18`）：

- 仅接收文件输入（不接任意内存波形、不要求在线计算先落盘）；不做深度/厚度转换、包络滤波、同步跟随门或跨波形跟踪。
- 区域批量取值保持请求区域的位置对应，逐点返回数值与状态（区分输入无效、缺输入、未检出、有效零值），不把损坏/解码/I/O 错误伪装为普通无效点。
- 前沿取值同时返回**同一点的位置/时间与对应幅值**（[ADR-0012](decisions/0012-basic-access-confirmed-and-deferred.md)），保留本次取值条件与输入来源；具体判据等待用户统一提供算法参考。

## 2. 逻辑模型、中立容器与物理引擎参考抽象

<a id="logical-model"></a>
### 2.1 对外中立容器与分模式 Schema 模型（现行）

SDK 对外数据组织采用 **极薄中立交付容器外壳（主采集容器 / 旁路派生容器）+ 文件内独立轻量 `Region` 实体 + 分扫描类型独立清晰的 Schema**（[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)、[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)）：

```text
PrimaryFile（file_role = Acquisition；不变 FileInstanceUUID；Artifact/Workpiece 与 Run 为可选元数据）
  ├─ Region 集合（文件内轻量独立实体：RegionID、Name、可选包围盒/参考系、VendorExtension；可合法留空）
  └─ Scan 集合（正常封存需 >=1 个已完成 Scan；每个 Scan 含独立 ScanID、模式 Schema 身份与显式 EndStatus）
       ├─ 模式 Schema 类型标识：SingleProbe / PhasedArray（首版）；预留 FMC / FeatureOnly
       ├─ EndStatus：正常完成 / 主动提前结束 / 故障中止及原因
       ├─ 引用 RegionID[0..M]（M:N 关联；可选指向文件内复检原 ScanID/RegionID）
       ├─ 固定采集解释（不可变）：最小解码必填核（SignalDescriptor、采样轴、通道/PA 阵元与聚焦法则映射）
       │                      + DICONDE/NeXus 强类型可选物理表 + 轻量参数化曲面几何 + VendorExtension
       ├─ 帧观测主体（固定列式 Schema）：
       │    ├─ 原始波形路径：样本 + LSB-first 位图 + 可选位置/pos_valid/同步等级 + 可选 CellCoord + 附加记录
       │    └─ 仅特征路径（预留）：独立不可变特征表（不虚构波形或波形位图）
       └─ [可选] 采集期伴生 C 扫快照（仅封存前 Write-Once 写入一次，统一快照模型，带来源与采用参数）

DerivedSnapshotFile（file_role = DerivedSnapshot；独立 Write-Once HDF5 容器，强绑定 source_file_uuid + ScanID）
  └─ 离线派生 C 扫快照集合（与伴生快照同一逻辑模型；更新替换通过临时文件 + 原子 rename 保证失败保旧）
```

### 2.2 原始波形物理引擎参考抽象（适用于原始波形路径）

下表保留为**共享底层物理 I/O 引擎**在承载原始波形模式（单晶 / PA / 后续 FMC）时的参考抽象（[ADR-0001](decisions/0001-stream-groups.md)），不强加于仅特征采集或未来模式 Schema 的外部形态：

| 符号/术语 | 含义 |
|---|---|
| `Scan` | 一次扫描主体；持有固定方案、模式解释、局部 Frame 轴与提交记录，不等于网格或图像 |
| `EventDefinition` / `e` | 固定方案中的发射事件槽位；跨帧复用，不是逐帧发射快照 |
| `WaveformStream` / `k` | 固定事件下固定接收输出的跨帧序列，Scan 内身份唯一；不必等于硬件通道或 dataset |
| `StreamGroup` / `g` | 同构流组：组内各流 dtype、样本数 `S_g`、样本表示与采样间隔一致，逐流差异以流表保存；每流静态属于唯一一组，组内序号 `q` |
| 组解释 | 通道组（单晶）、PA 声束集或 Tx×Rx 矩阵（后续 FMC）；解释属于流组 |
| 帧级附加记录 | Scan 内固定列式声明、按列标明 `required`/`nullable`、每帧一行的带类型记录（含原始帧位置、同步等级、可选 `CellCoord`、时间戳、来源 ID） |
| `Frame` / `n` | 一次结构闭合的组合记录及零起点索引，包含各流组第 n 行、帧位置及帧级附加记录 |
| `N` / `E_x` / `N_r` | 提交记录权威完整前缀长度（u64）/ 物理 dataset extent（可大于 N）/ 恢复模式验通前缀长度 |
| `B` / `K` / `K_g` | Batch 帧数（B≥1）/ Scan 流总数 / 流组 g 流数；PA 声束数记为 `N_b` |
| `S_g` / `τ_g` / `s` | 流组 g 固定样本数、原始 dtype 与样本索引（单流引用作 `S_k`、`τ_k`） |

物理引擎下原始波形的逻辑身份为 `(Scan,n)`、`(Scan,n,e)`、`(Scan,n,k)`、`(Scan,n,k,s)`，按 `(g,q)` 定位存储与 Core I/O。同一硬件接收通道在不同事件下可映射不同流；接收输出必须辨识单接收阵元或固定接收法则合成波形等数据层次，不得从 shape 猜测。

<a id="scan-01"></a>
### SCAN-01：中立文件容器、Region 与独立 Scan〔确定〕

- 文件须支持枚举其中的独立 `Region` 实体与 `Scan` 集合；工件与 Run 身份为可选带类型元数据。每个 `Scan` 独立持有模式 Schema、固定定义、结束状态（`EndStatus`）、Frame 轴、位置关联与完整前缀；同文件内不同 `Scan` 不通过同名跨 Scan 隐式复用定义（跨 Scan 定义去重不在首版范围）。
- **新建 Scan 与不可重开追加（`D-15` 已关闭）**：分块、停止后重新扫描、复扫、精扫、换探头、重装、重标定或固定定义改变须创建新 Scan，不修改旧 Scan；段内暂停留在同一 Scan 内。同一未封存 Writer 会话可顺序完成当前 Scan 后创建下一 Scan（不支持交错写多个活动 Scan）；**文件一旦封存或干净关闭，不支持重新打开追加原始波形或新原始 Scan**（[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)），离线派生结果一律写 Write-Once 旁路/新目标文件。跨文件复检关系归 `D-19`。

<a id="scan-02"></a>
### SCAN-02：文件内 Region 实体与引用约束〔模型已定，字段名待 M2〕

按 [ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)，文件内 `Region` 为轻量元数据实体（`region_id`、`name`、可选包围盒/参考系标识与带类型 `VendorExtension`，不含复杂几何引擎），与 `Scan` 构成 **M:N 引用**（单 Scan 可选关联 `0..N` 个已声明 `Region`，多 Scan 可共享同一 `Region`；未采集区域可合法留空）；文件内复检由新 `Scan` 可选指向原 `ScanID`/`RegionID`（须引用文件内已存在身份，拒绝悬空引用）。`D-11` 仅剩 M2 精确字段名与 wire 序列化细节。跨文件复检归 `D-19`，Run 映射留调用方。

<a id="rec-01"></a>
### REC-01：共同记录身份〔确定〕

原始波形路径下，Scan 内所有流共用共同 Frame 轴；采集层归组并一次提交完整 Frame 或批次，SDK 不等待逐流拼装、不做时间配准或帧号回绕展开（由上游适配层提交单调帧序）。共同 Frame 轴与重复位置值都不合并 Frame 身份、也不证明规则网格、空间邻接或运动同步；无有效数据的波形槽位使用 [STA-01](#sta-01) 有效位与零填充表达。

<a id="rec-02"></a>
### REC-02：计数、extent 与边界〔确定〕

`N` 范围为 u64（`0 <= n < N`），所有计数、索引、切片与字节长度运算必须防 32 位静默截断或溢出，实现上限低于 u64 时须显式报错。物理 dataset extent `E_x`、fill value 与提交记录权威计数 `N` 必须严格区分：不得暴露 `n >= N` 尾部；必要对象在 `[0, N)` 内缺行或关联断裂时必须报结构错误，不得静默缩短宣称完整。

## 3. 身份、版本与元信息

<a id="id-01"></a>
### ID-01：解释身份〔确定模型，wire 编码待 M2〕

文件必须携带可识别的容器角色（`Acquisition` / `DerivedSnapshot`）、容器格式版本（`format_major.format_minor`）、**SDK 分配的不变 `FileInstanceUUID`**（旁路容器额外强绑定 `source_file_uuid` + `source_scan_id`）、`Scan`/`Region`/伴生快照稳定 ID（工件与 Run 为可选元数据）、**采集模式 Schema 身份与独立 Schema 版本**（`SingleProbe`/`PhasedArray`，预留 `FMC`/`FeatureOnly`，不靠 shape 猜测）和**物理布局身份**。文件公共描述与 Scan 专属描述作用域严格隔离。读取器遇不理解的 `format_major`、未知必要能力、模式 Schema 或 layout 必须明确拒绝，不得按设备默认值猜测（版本解耦规则见 [SDK_CONTRACT.md](SDK_CONTRACT.md#versioning)）。

<a id="id-02"></a>
### ID-02：必要能力与可选扩展〔确定〕

区分**影响当前请求解释的必要语义/filter/结构编码**与**可安全跳过的可选辅助块**：未知可选辅助块可跳过；未知必要编码、语义或缺失解码器不得静默忽略。若无法验证位置结构编码但仍可验证波形及记录范围，可显式降级提供受限波形访问并明确报告位置不可用，不得伪造零坐标；若连记录前缀边界也无法验证，则严禁降级放行。

<a id="meta-01"></a>
### META-01：公共描述与带类型/版本的内容〔确定〕

元信息采用 **最小解码必填核 + 强类型标准可选物理表 + 带 `(vendor_id, schema_uri, version)` 的可选 `VendorExtension`**（[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)）。公共描述声明关联对象、作用域及类型/版本；Core 保证保存、独立读取与关联引用，不得把关键解码或采样解释藏进无约定扩展字典。

## 4. 波形、状态、位置与参数（原始波形存储契约）

> 说明：本节 `WAV-*` 与 `STA-01` 约束实际保留原始波形的采集路径；预留的仅特征采集走独立不可变 Schema，不要求虚构波形或波形有效性位图（[RET-01](#ret-01)）。

<a id="wav-01"></a>
### WAV-01：流组内固定、支持 dtype 与自解释〔确定〕

在原始波形物理抽象中，每个流组 `g` 的逻辑样本形状为 $X_g \in \tau_g^{N\times K_g\times S_g}$。`S_g`、`τ_g`、样本表示与采样间隔在组内一致并在所属 `Scan` 内固定，逐流差异以流表保存；跨组可异构（单流可独占 `K_g = 1`）。

- **首版支持 `dtype`（[ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md)）**：`{i8, u8, i16, u16, i32, u32, f32}`，首版显式拒绝 `f64` 与复数类型。
- **`SignalDescriptor`**：固定描述须完整包含原始位宽/dtype、字节序、有效 ADC 位与对齐、偏置与比例、采样轴与起点延迟，以及 `RawRF / Rectified / AnalyticEnvelope / LogDb` 等信号处理层次标签，以便离线复用采集侧 `Ingress Decode` 并保留 ADC 顶格饱和证据，不得仅存驱动函数名。

<a id="wav-02"></a>
### WAV-02：严格接收与无损保存〔确定〕

`valid=1` 的波形必须与所属流组的固定长度和 `τ_g` 严格一致；SDK 校验身份、shape/dtype、容量与引用，不做业务幅值或成像合法性判定，也不隐式截断、补齐、重采样或数值转换。`valid=0` 的槽位可省略样本（稠密缓冲对应输入被忽略；Writer/Scan 级严格模式下出现非零样本则拒绝整个写调用）。标记有效且通过校验的整数样本按原生数值语义无损回读；**`f32` 按 IEEE-754 逐位无损保真**（不规范化 `NaN` payload 或改写 `-0.0`，[ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md)）。

<a id="sta-01"></a>
### STA-01：单一有效性位图与零填充〔确定〕

仅用于实际保留的原始波形槽位 `(Scan,n,k)`，粒度为整条波形（1 bit：`valid=1` 或 `valid=0`）：

- **显式提交完整位图（[ADR-0003](decisions/0003-explicit-validity-bitmap.md)、[ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md)）**：存储层与 C11 ABI 统一采用 **LSB-first packed bitset**（每帧每组 `ceil(K_g / 8)` 字节，高尾部位强制清零并校验）。每次写调用须为调用内全部 Frame 的全部槽位给出有效位；缺失、长度不符、尾部位非零或身份不匹配时拒绝整个调用；严格模式按 Writer/Scan 创建选项开启。
- **有效全 0 vs 无效零填充**：`valid=1` 时即使全 0 样本也视为真实回波无损保存；`valid=0` 逻辑上呈全 0 填充值且交付时与位图一同返回、不跳过槽位，禁止仅凭全 0 推断无效或把填充值当作真实回波。预分配填充不授权暴露 `n >= N` 尾部，存储损坏或 I/O 错误也不得降级为 `valid=0`。

<a id="pos-01"></a>
### POS-01：采集时位置绑定〔确定〕

支持无空间位置的纯时间/顺序扫描（不伪造零坐标）。需要空间的扫描中，**波形有效但位置获取失败时必须保全有效波形**，并通过显式 `pos_valid = 0` 标记位置未知/无效（不靠浮点 `NaN` 猜无效，无效时位置槽位零填充，[ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md)）；波形有效位与位置状态彻底正交。位置绑定严格按 Frame 索引，不靠时间戳、浮点相等或最近邻搜索；历史采集位置不可被后处理静默覆盖。

<a id="pos-02"></a>
### POS-02：固定列式位置描述、同步等级与帧级附加记录〔确定〕

- **位置与同步可靠性等级（[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)、[ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md)）**：`Scan` 固定定义静态声明位置模式（`None` 或具名原始传感器/笛卡尔/姿态结构，含类型/版本/字段/单位/参考系/来源）以及 Scan 级默认同步可靠性等级（`HardwareSynchronized` / `StepAndShootVerified` / `SoftwareTimestampPaired` / `Unavailable`；若逐帧变化，可附带帧级同步等级列）；不做强制坐标变换或网格插值。
- **可选离散 `CellCoord[Frame]`**：定长整型列（`int32[1..3]`）并携带帧级无归属有效标记（合法表达转场/跳点帧无网格归属），无规则布局时省略，不做浮点分箱。
- **帧级附加记录**：时间戳、理论坐标、来源 ID 等其他每帧内容统一采用固定列式 Schema，在 `Scan` 初始化时**逐列声明 `required` 或 `nullable`（带显式 valid 位）**，同 Frame 同一提交单元写入；首版禁止晚到补写。

<a id="pa-01"></a>
### PA-01：唯一帧位置与派生声束解释〔确定〕

PA 声束集第 `n` 帧原始关系为 `Frame_n = (P_n, {W_n,b}, 状态与关联)`，**同帧全部 `N_b` 个声束共用唯一帧级原始位置 `P_n`**，不为每条声束重复复制原始位置；声束空间定位依赖 `P_n + 固定探头/几何 + 对应聚焦法则`。束号必须静态关联正确事件与接收输出（不与法则、硬件通道或阵元混用），派生声束坐标不覆盖 `P_n`。多独立运动探头位置模型归 `D-13`。

<a id="par-01"></a>
### PAR-01：固定采集定义的作用域与复用〔确定〕

Scan 共享设置、每个事件设置、流组共享采样表示与组内流表均在所属 Scan 作用域内固定并只保存一次（预定程序如 `L0, L1, L2` 周期循环不属于参数修改）。方案、流组划分、流长度/dtype 或采样解释发生真实变化须新建 Scan（[SCAN-01](#scan-01)），不可维持旧 Scan 身份或记录逐帧 `config_index`。在线特征门参数变动历史区分按 [SNAP-01](#snap-01) 处理。

<a id="par-02"></a>
### PAR-02：旧动态快照字节区〔已替代〕

`data + offsets` 动态快照字节区已被 [PAR-01](#par-01) 取代，仅保留编号作历史追踪，不再使用。

<a id="fmc-01"></a>
### FMC-01：固定 Tx/Rx 映射与覆盖〔确定语义，FMC 模式预留〕

Tx×Rx 矩阵是流组解释（`FMC` 模式在首版 Schema 类型枚举中保留预留口，不展开首版工程字段，[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)）：有序发射集合 `I`、接收集合 `J` 与显式映射 $\pi$ 定义 $M_n[i,j] = X_{\pi(i,j)}[n,:]$（首版单矩阵限于单个流组，[ADR-0009](decisions/0009-review-contract-clarifications.md)；跨组矩阵及 HMC/PWI/Sparse 部分矩阵归 `D-14`，不得借 `valid=0` 冒充未采集对）。声明为完整矩阵时必须覆盖全 `I×J`，有序对映射唯一且与事件发射/接收输出身份一致，禁止互易对复用或从目录顺序推断。

<a id="fmc-02"></a>
### FMC-02：矩阵访问与异构结果〔确定语义，FMC 模式预留〕

纯选择层在一个明确 Frame 内支持完整矩阵、固定 Tx 行、固定 Rx 列、有序 Tx×Rx 子矩阵、显式收发对清单及样本选择，与流/单波形视图共享同一原始来源。选定单元同构时交付逻辑轴序 `[Tx,Rx,Sample]`（Batch 加帧轴）及有效性位图（不承诺物理连续或零拷贝），共同时间轴还须采样解释一致；异构时返回带 Tx/Rx 身份的分单元结果，不隐式转换。

## 5. HDF5 组织边界与正式写入保护机制

<a id="map-01"></a>
### MAP-01：逻辑语义与可配置三维分块组织〔机制已定，wire 路径待 M2〕

写出文件使用 HDF5 2.x 库并限定 `libver` 为 `v1.10–v1.14` 可读（[ADR-0005](decisions/0005-file-format-range.md)，不使用 2.0 专有特性，单 chunk < 4 GiB）。在解除 `h5py` 裸翻内部路径约束（[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)）后，物理布局彻底围绕读写效率设计：

- **可配置三维物理分块（[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)）**：原始流组样本支持在 Scan 固定定义中声明 `(F_chunk, K_chunk, S)` 块几何（单波形 `S` 维不切分），首版默认 `K_chunk = K`、按 ~1–4 MiB 目标未压缩块大小自适应 `F_chunk`（支持写入方覆写）。
- 下列逻辑边界必须可由 SDK 完整独立解释（精确 HDF5 路径与属性编码在 M2 wire 规范闭合，`D-07`）：

| 逻辑对象 | 逻辑范围与职责 | 规则与阶段 |
|---|---|---|
| 容器角色、Region 与 Scan 集合 | `file_role`、`FileInstanceUUID`（旁路附原文件/Scan 绑定）、可选工件/Run 元数据、轻量 M:N `Region`、`Scan` 枚举与 `EndStatus` | `SCAN-01/02`、`ID-01`；M2 wire（`D-07`/`D-11`） |
| 解释身份与模式 Schema | 容器版本、模式类型与独立 Schema 版本（`SingleProbe`/`PhasedArray`，预留 `FMC`/`FeatureOnly`）、物理布局标识 | `ID-01`；M2 wire（`D-07`） |
| 固定定义与元信息 | 最小解码必填核、`SignalDescriptor`、DICONDE/NeXus 可选物理表、参数化曲面几何、流组/PA 映射、`VendorExtension` | `META-01`/`PAR-01`/`REL-01`；字段清点（`D-09`） |
| Frame 轴与帧级列式记录 | 帧位置、`pos_valid`、同步等级、可选 `CellCoord[Frame]`（含无归属位）、`required`/`nullable` 附加记录 | `POS-01/02`；`ADR-0019` |
| 波形主载荷与位图 | 原始流组样本 `[N,K_g,S_g]`（`(F_chunk, K_chunk, S_g)` 分块）与 `[N,ceil(K_g/8)]` LSB-first 位图 | `WAV-01`/`STA-01`；`ADR-0017/0019` |
| 前缀、提交记录与生命周期 | 各 Scan 双槽提交记录、逐块 `XXH3-64` 校验表、完成/失败标志、文件封存状态 | `WRT-02`/`LIF-01/02`/`MAP-02`；`ADR-0018/0019` |
| 伴生与旁路快照 | 统一快照模型（2D 栅格/稀疏点表 + 状态 + 来源 + 参数）；封存前伴生写 1 次，离线写 Write-Once 旁路容器 | `SNAP-01`；M2 wire（`D-16`） |

`E_x > N` 预分配不等于已提交；重写含已 Flush 数据的压缩 chunk 时 HDF5 会原地覆写或释放复用空间，曾实测导致崩溃损坏（[ADR-0002](decisions/0002-durability-and-failure.md)）。

<a id="map-02"></a>
### MAP-02：正式写入保护机制（只写一次 + 按 Scan SWMR）〔确定〕

已由 [ADR-0018](decisions/0018-storage-engine-swmr-and-strict-lifecycle.md) 正式选定为 Core 写入保护基线（须在 M2 补一次单 Scan 数千块多级块索引 SIGKILL 复核，`D-05`）：

1. **物理块只写一次**：写端按流组与 `(F_chunk, K_chunk, S)` 组装整块、在 HDF5 全局锁外并行编解码并计算 `XXH3-64`，以 `H5Dwrite_chunk` 直接写块（绕过块缓存）；Scan 完成时尾块补零只写一次。
2. **按 Scan 启用 SWMR**：每个 Scan 在非 SWMR 下建齐对象后立即进入 SWMR 写模式追加帧；完成 Scan、新建下一 Scan 或封存前写伴生快照时，SDK Writer 在持续持有自身写者锁的前提下透明关闭并重开非 SWMR HDF5 句柄（SWMR 属内部实现，不外泄为公共 API）。
3. **Flush 尾部日志与双槽提交**：Flush 时将半满尾块写入 A/B 双槽尾部日志（不改主数据集），先 `H5Fflush` 数据与日志再写双交替槽提交记录（序号、有效行数、校验链、`record_checksum`）并再次 `H5Fflush`（不要求 `fsync`，[ADR-0008](decisions/0008-process-crash-scope.md)）。
4. **恢复与原地只读**：SWMR 期间崩溃走标准 SWMR 只读恢复；非 SWMR 短暂建对象/封存窗口崩溃走原地只读打开（内存清除 superblock 状态位，优先公开只读 VFD，绝不复制百 GB 文件或修改源文件）。选取 `seq` 最大且校验有效的提交记录，主数据集完整块＋日志尾块逐块校验 `XXH3-64`；双槽提交全毁则该 Scan 判不可恢复（`N_r = 0`）。
5. **push 两阶段读**：先读入并校验本次所需全部物理块的 `XXH3-64`，再解码至调用者目标（暂存有界），确保存储损坏在改写目标前发现。

## 6. 写入、持久化与 Write-Once 生命周期

> 原始主文件与旁路派生文件均遵循 Write-Once 封存不可变；完整状态转移图与 C ABI 约束见 [SDK_CONTRACT.md](SDK_CONTRACT.md#lifecycle-state)。

<a id="wrt-01"></a>
### WRT-01：提交单元、前置校验与写失败态〔确定〕

- **前置整批校验**：每次写调用的 Frame 批次（属于单一活动 Scan）必须作为一个整体在写入文件或推进提交记录前完成校验：Scan 身份、完整显式 LSB-first 位图（含尾部位零校验）及流身份、有效波形存在性/shape/dtype、位置状态与必需帧级记录、容量与固定引用；任一项不合格则整个调用拒绝，文件与提交前缀丝毫不变，提交状态报告 `NOT_COMMITTED`。
- **同步消费与写失败态**：允许阻塞、无取消，输入缓冲在返回后不保留借用。写/Flush/完成 Scan/伴生快照/封存中发生任何 I/O 错误时按 [IO-01](#io-01) 失败并使 **Writer 进入写失败态**（**一律禁止原位重试或继续追加**，[ADR-0018](decisions/0018-storage-engine-swmr-and-strict-lifecycle.md)）；失败态仅允许**放弃并关闭**，或在全部已提交数据通过深度校验后**带失败标记封存**。

<a id="wrt-02"></a>
### WRT-02：提交记录、完整前缀与不可变历史〔确定〕

每个 `Scan` 独立维护双槽提交记录（已提交帧数 `N`、各对象有效行数与校验链），它是可见范围的唯一权威（`E_x` 仅物理上界）。推进提交记录前相关样本/位图/帧级记录/定义依赖须已完成写入步骤；已提交物理块严禁被重写或复用空间，每个物理块须同时带存储字节与解码后字节的 `XXH3-64` 校验值（`VAL-01`），作为历史未受损的独立核对依据。已提交历史不得修订或晚到补写。

<a id="wrt-03"></a>
### WRT-03：显式 Flush 与成功后条件〔确定〕

普通写入不承诺立即落盘。显式 `Flush`（以及隐含 Flush 的 `完成 Scan` / `封存文件`）返回成功后保证：**此前全部已写入数据及其解释元数据，在之后任意时刻发生进程崩溃后，均能由 [LIF-02](#lif-02) 恢复模式完整恢复并通过校验。**

- **崩溃边界（[ADR-0008](decisions/0008-process-crash-scope.md)）**：只覆盖进程崩溃，要求将数据交给操作系统页缓存（`H5Fflush`），**不要求 `fsync`**；断电、操作系统崩溃与存储介质故障不在保证范围，也不作相应验收。`Flush` 失败使 Writer 进入失败态，但不撤销此前已成功 Flush 的后条件。

<a id="io-01"></a>
### IO-01：调用级强原子性〔确定〕

每次读写调用是一个成功/失败单元，遇 I/O 错误、越界/空选择或损坏解码失败必须整体失败并返回稳定错误码（不得悄悄缩短数量交付部分结果）：

- **push 读失败**：调用者样本、位图与关联目标缓冲逐字节保持调用前原样（由 [MAP-02](#map-02) 两阶段读兑现，[ADR-0018](decisions/0018-storage-engine-swmr-and-strict-lifecycle.md)）。
- **poll 读失败**：不发布新视图；旧借用期已在该次调用开始时结束（[BUF-01](#buf-01)）。
- **写失败**：不新增提交，已提交数据经校验核对保持不变（可留下不可见未提交空间），Writer 进入失败态。
- **提交状态与绑定隔离**：写入类调用独立返回 `COMMITTED / NOT_COMMITTED / UNKNOWN`；原生已提交但语言绑定层构造失败时不得伪装成未提交供调用方盲重试（[SDK_CONTRACT.md](SDK_CONTRACT.md#c-abi-rules)）。

<a id="lif-01"></a>
### LIF-01：Scan 完成、严格非空对象与 Write-Once 封存〔确定〕

- **文件三条生命周期**：① 初始化 → 顺序写入 Scan（至少 1 个已完成 Scan）→ 封存前可选写入 1 次伴生 C 扫快照 → 正常封存（含底层 `H5Fclose`）；② 写入失败态 → 带失败标记封存（其中活动 Scan 保持未完成并标记失败原因与已提交范围，[ADR-0009](decisions/0009-review-contract-clarifications.md)）或放弃关闭；③ 未封存即关闭（含崩溃）→ 视为未正常关闭，交 [LIF-02](#lif-02)。
- **Scan 生命周期、结束状态与严格非空（[ADR-0018](decisions/0018-storage-engine-swmr-and-strict-lifecycle.md)）**：定义/初始化 → 追加（含段内暂停）→ 完成（`EndStatus = 正常完成 / 主动提前结束 / 故障中止`）。完成 Scan 隐含 Flush 并写入完成/校验记录，此后拒绝向该 Scan 追加；上一个 Scan 未完成时拒绝创建新 Scan。**正常完成 Scan 须至少已提交 1 帧（`N >= 1`），正常封存文件须至少包含 1 个已完成 Scan（`n_scans >= 1`）**；0 帧无数据中止直接放弃删除，同时正常封存文件允许包含已声明未采集的空 `Region` 实体。
- **Write-Once 不可变与不重开（`D-15` 已关闭，[ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md)、[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)）**：正常读取仅面向已封存文件；**原始文件封存后彻底只读不可变，封存或干净关闭后均不支持重开追加原始数据，也禁止原地替换其伴生快照**。离线派生快照一律写入 Write-Once 旁路派生容器或另存新目标（[SNAP-01](#snap-01)）。

<a id="lif-02"></a>
### LIF-02：尽力只读恢复〔确定〕

未正常关闭文件（含已写封存标记但 `H5Fclose` 前崩溃的文件）必须通过显式只读恢复模式处理（严禁在正常重开时静默当作正常文件，也不得自动删改或原地截断源文件）：

1. **原地只读保护**：绝不改写源文件、不复制百 GB 文件；SWMR 期间崩溃走标准 SWMR 只读打开，非 SWMR 短暂窗口崩溃在内存中清除 superblock 状态标志（优先公开只读 VFD；推荐独立进程隔离解析损坏文件风险）。
2. **逐 Scan 核验与双槽全毁处理（[ADR-0018](decisions/0018-storage-engine-swmr-and-strict-lifecycle.md)）**：依据各 Scan 有效提交记录建立候选前缀并逐块核对 `XXH3-64`，暴露通过校验范围 `N_r`（不凭 extent 猜长度）；双槽提交记录均校验失败时直接判该 Scan 不可恢复（`N_r = 0`），不盲扫猜长度。区分并报告“声明范围、验证范围、失败对象与未执行检查”，某 Scan 受损不得静默缩短其他 Scan。
3. 尽力恢复不预设固定时间窗，但不能免除 [WRT-03](#wrt-03) 的 Flush 后条件，也不得将损坏尾部改成 `valid=0` 伪装正常。

## 7. 读取语义与内存规模

<a id="read-01"></a>
### READ-01：独立和绑定访问〔确定〕

Core I/O 每次请求指定一个 `Scan`、连续区间或离散帧清单及一个或多个流组（选定组内全部或通过选择层过滤）；并支持识别 `FileInstanceUUID`、枚举文件内 `Region`（可选工件元数据）与 `Scan`（不可默认“第一个或最新 Scan”，也不跨 Scan 拼接/重采样）。关联读取保持与波形/位图/位置/同步等级/元信息的同 Frame 一致性；等效条件下（不随 `poll`/`push`、分析/Batch 或先前读取改变）返回相同数据，读取本身永不修改文件。

<a id="read-02"></a>
### READ-02：选择结果语义与整体拒绝〔确定〕

帧内流、声束、Tx/Rx、收发对与样本选择作为**纯选择层**作用于 Core I/O 结果（不直接做磁盘 I/O）：

- 有序清单（如声束 `[2,0,2]`、样本 `[3,1,3]`）与离散帧清单必须**保序保重复**，不得暗自排序或去重；Batch 保持声明的 Frame 顺序与全部关联。
- Tx 清单 × Rx 清单为笛卡尔交叉子矩阵；显式收发对清单仅返回列出项，不展开矩阵。
- 样本切片 `[a,b)` 或清单按每个选中流自己的固定长度 `S_k` 校验边界；**局部越界与空选择（`B == 0` 或空流清单）一律整体拒绝**（[ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md)），严禁静默截断或补齐；`valid=0` 是正常数据状态（返回零填充和位图），I/O 错误不降格为无效槽位。

<a id="read-03"></a>
### READ-03：分析读取、双模式 Batch 与容量查询〔确定〕

支持**常规分析读取**（数据＋位置/状态/元信息引用）与 **Batch 消费**（同 Scan `B ≥ 1` 帧，同时支持**连续区间 `(start, count)`** 与 **离散帧清单 `[n_0, n_1, ...]`**，离散清单内部按物理块合并去重读盘，[ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md)）。跨流组采用**每组独立稠密缓冲**交付 `[B,K_g,S_g]` 样本与 `[B,ceil(K_g/8)]` 位图，并提供不结束 `poll` 借用的块几何与字节容量查询 API（细节见 [SDK_CONTRACT.md](SDK_CONTRACT.md#core-io-batch)）。两种内容交付维度正交于 `poll`/`push` 所有权，均不得要求全扫描驻内存；主机视图不等于 GPU 设备指针或零拷贝承诺。

<a id="buf-01"></a>
### BUF-01：poll/push 缓冲与同步生命周期〔确定〕

| 模型 | 同步行为与所有者 | 有效期与失效边界 |
|---|---|---|
| `poll` | SDK 读/解码至内部主机缓冲，返回只读借用视图（禁止调用者修改或释放） | 至**同一 Reader 下一次样本/位置/帧记录读取调用开始**（无论成功、失败或参数拒）或 **Reader 关闭**（[ADR-0004](decisions/0004-concurrency-and-borrow-scope.md)）；目录/元信息/块几何与容量查询不使其失效 |
| `push` | 调用者提供可写缓冲＋64 位字节长度，SDK 两阶段同步校验并复制（失败按 [IO-01](#io-01) 逐字节不变） | 完全由调用者管理（适配上位机固定缓冲池 `Batch-of-SoA` 及 >2 GiB 非托管内存），Reader 关闭或其他读取均不使其失效 |

单 Reader 同时只有一份 `poll` 视图；异步 GPU 上传双缓冲需用 `push` 或两个 Reader。`.NET` 绑定的代数令牌受检视图与非托管缓冲合同见 [SDK_CONTRACT.md](SDK_CONTRACT.md#dotnet-binding)。

<a id="cap-01"></a>
### CAP-01：超 RAM 访问〔确定〕

支持大于 100 GB、工作集远超物理 RAM 的单文件：读/写内部工作内存与缓存必须有界（不随 Scan 数量或总帧数 N 线性增长）；打开文件不要求全量加载波形或所有 Scan 定义。单 Frame 不提供帧内分块交付，单 Frame 超限或请求超限须显式拒绝；峰值预算口径须统筹计入调用者目标、SDK 原子暂存/整块组装缓冲、HDF5 解码与绑定副本（`D-02`/`D-03`）。

## 8. 压缩与解码

<a id="cmp-01"></a>
### CMP-01：无损压缩与精简内置编码链〔确定〕

无损压缩须满足 [WAV-02](#wav-02)，且完整编码链与参数必须记录在标准可识别位置（HDF5 filter 链），严禁藏入未声明的私有封装；缺失解码器或不支持参数时必须明确报错，不得回退错误数值。按 [ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md)，首版 SDK 静态内置且仅支持 **`none`**、**`shuffle + zstd`（默认低级别）** 与 **`shuffle + lz4`（高吞吐可选）**（使用标准 HDF5 注册 filter ID：`H5Z_FILTER_SHUFFLE`、`32015` Zstd、`32004` LZ4；不内置 `deflate`），天然衔接未来 M4 GPU `nvCOMP` 解压。

<a id="cmp-02"></a>
### CMP-02：GPU 可选能力的声明〔确定，归 M4〕

CPU 解码可读是基础保证，GPU 直接解压为独立可选加速能力（`D-06`）：只有当“磁盘压缩块 → 传输 → GPU 解码＋预处理逆变换＋尾块”全链路与 CPU 解码逐值一致并通过端到端测量后，方可声明支持（主机 CPU 解压后再 H2D 不算 GPU 解压）。

## 9. 符合性检查与统一逻辑不变量

<a id="val-01"></a>
### VAL-01：分层、可追溯的验证报告〔确定〕

检查分层推进：**识别**（格式/容器角色/UUID/模式 Schema/版本/解码依赖）→ **结构**（组型/shape/定义/位图/提交记录）→ **关联**（前缀/位置与同步等级/Region 引用/事件与接收输出/PA 或预留 FMC 映射）→ **深度**（逐块存储与解码 `XXH3-64` 校验值）。校验值不匹配为硬文件错误；结果区分 `PASS / FAIL / NOT_RUN / BLOCKED / UNSUPPORTED`，明确标注 Spec 修订与 test-only 说明，未运行或待定阻塞不得伪称通过。

<a id="invariants"></a>
### 本轮统一逻辑不变量

`U-01`–`U-16` 用于设计与验证追踪，不分配 wire 字段或错误码：

| 规则 | 必须保持的性质 | 细节入口 |
|---|---|---|
| <a id="u-01"></a>U-01 | HDF5 2.x 写出 1.10–1.14 可读格式；按扫描类型提供独立清晰 Schema，不靠 shape 猜测模式；不承诺 `h5py` 裸翻内部路径 | DOC-01、ID-01、MAP-01 |
| <a id="u-02"></a>U-02 | Scan/事件/流组采集定义在 Scan 内固定只存一次；固定程序循环不产生逐帧配置历史 | PAR-01 |
| <a id="u-03"></a>U-03 | 原始波形可追溯到 Frame、事件与接收输出（区分阵元与合成信号）；流静态属于唯一组；流不等同于硬件通道 | 逻辑模型、REC-01 |
| <a id="u-04"></a>U-04 | 流组内 dtype/长度/采样解释固定，组间允许异构，整数原生无损、`f32` 按位无损，完整保留 `SignalDescriptor` | WAV-01/02 |
| <a id="u-05"></a>U-05 | PA 同帧全部声束共用唯一帧级原始位置 `P_n`；显式 `pos_valid` 与同步等级；其他帧级附加记录按帧关联不覆盖 `P_n` | POS-01/02、PA-01 |
| <a id="u-06"></a>U-06 | FMC 显式固定 Tx/Rx 映射，行列不互换，互易对独立；单矩阵限于单个流组（首版预留） | FMC-01 |
| <a id="u-07"></a>U-07 | 矩阵/流组/流/单波形共享同一来源；组内稠密交付，异构不强行补齐转换 | FMC-02 |
| <a id="u-08"></a>U-08 | 原始波形槽位采用单一 LSB-first packed bitset，写入显式提交并校验尾部位零；有效全 0 保真、无效零填充，错误不降格为无效位 | STA-01、WRT-01、LIF-02 |
| <a id="u-09"></a>U-09 | 选择层为纯函数，保序保重复、交叉与配对分开、样本边界逐流检查；局部越界与空选择整体拒绝；Batch 保留声明帧序与关联 | CORE-01、READ-02/03 |
| <a id="u-10"></a>U-10 | 波形、状态、位置、帧级记录、元信息与固定引用关联一致；位置失败保全有效波形且不写假零坐标或靠 `NaN` 猜无效 | READ-01、POS-01/02、META-01 |
| <a id="u-11"></a>U-11 | 分析/Batch（连续与离散）、poll/push 与单帧等效读取一致；poll 借用期与 push 两阶段原子性严格守界；原始与旁路文件封存后均 Write-Once 不可变 | READ-01/03、BUF-01、CAP-01、SNAP-01 |
| <a id="u-12"></a>U-12 | 原始采集历史与伴生快照不可篡改，仅特征不可被覆盖；合规、算法、性能与恢复分开验证 | WRT-02、RET-01、VAL-01 |
| <a id="u-13"></a>U-13 | 中立容器分配不变 UUID，独立承载轻量 M:N `Region` 与多个 `Scan`；正常完成/封存拒空对象；封存/关闭后不重开追加 | ID-01、SCAN-01/02、LIF-01/02 |
| <a id="u-14"></a>U-14 | 多 Scan 原始结果并存，不隐式融合或替代；不从容器或坐标重复推导覆盖或映射关系 | SCAN-01/02、READ-01、WRT-02 |
| <a id="u-15"></a>U-15 | 双槽提交记录为可见范围唯一权威（全毁不可恢复）；`MAP-02` + 按 Scan SWMR 保 Flush 后进程崩溃可恢复并通过 `XXH3-64`；写失败禁重试且不改历史 | WRT-01–03、IO-01、LIF-01/02、MAP-02 |
| <a id="u-16"></a>U-16 | 进程内 HDF5 全局串行；同一对象不并发；多 Reader 独立；已封存文件多进程只读；写期间 SDK 自检并拒绝同/跨进程 Reader | CORE-01、BUF-01 |

<a id="open-items"></a>
## 10. 待定项登记与闭合门槛

下表是全库唯一 `D-01`–`D-19` 状态登记表；`ADR-0016～0020` 已闭合全部 Core 首版架构与工程分叉，剩余项精确区分为 **已闭 / M2 细化 / 待补事实 / 后置**（详细推进清单见 [DECISION_DIRECTIONS.md](DECISION_DIRECTIONS.md)）：

| 编号 | 当前状态 | 已定结论与剩余缺口 | 权威依据 |
|---|---|---|---|
| D-01 | **方向已闭（M2 wire 细化）** | 固定列式 Schema、`pos_valid`、同步等级、`CellCoord[Frame]`（`int32[1..3]` + 无归属位）、按列 `required`/`nullable` 附加记录（禁晚到补写）均已定；M2 固化 HDF5 复合/列式编码 | ADR-0019 |
| D-02 | **dtype 已闭 / 规模待事实** | 首发 `dtype` 已定为 `{i8..u32, f32}`（按位保真，拒 `f64`/复数）；仍需真实 UMS 设备最大 Frame 字节数、持续速率与全链路峰值内存预算 | ADR-0019 |
| D-03 | **布局已闭 / 权重待事实** | 可配置 `(F_chunk, K_chunk, S)` + 离散帧按块合并解码已定；仍需五类场景实际访问比例与延迟/吞吐验收门槛 | ADR-0017 / 0019 |
| D-04 | **编解码与分块已闭 / M3 校准** | 内置 `none` / `shuffle+zstd`（默认）/ `shuffle+lz4`（去 `deflate`）及默认 1–4 MiB 目标块已定；M3 按真实波形实测微调默认块尺寸与 zstd 级别 | ADR-0017 / 0019 |
| D-05 | **机制已闭 / M2 压测复核** | 正式选定 `MAP-02` + 按 Scan SWMR、原地只读恢复、拒绝正常空对象、写失败禁原位重试、双槽全毁判不可恢复；M2 须补单 Scan 数千块多级索引 SIGKILL 证据 | ADR-0018 |
| D-06 | **后置（M4 可选）** | GPU `nvCOMP` 完整 filter 链解压一致性与端到端对比（不阻塞 Core M3） | CMP-02 |
| D-07 | **选型已闭（M2 wire 定稿）** | `XXH3-64`、HDF5 1.10–1.14、标准 filter ID、三套版本解耦与 `1.0` 冻结已定；M2 输出精确 HDF5 路径/属性/提交记录 wire 编码规范并通过独立读取器验通 | ADR-0005 / 0019 / 0020 |
| D-08 | **已闭合（M2 编码落地）** | 存储与 C ABI 统一 LSB-first packed bitset（尾部位清零校验）、Writer/Scan 级严格模式已定 | ADR-0003 / 0019 |
| D-09 | **分层已闭 / 设备字段待清点** | 最小解码必填核 + DICONDE/NeXus 强类型可选物理表 + 轻量参数化曲面几何 + `VendorExtension` 已定；M2 前对照首批单晶/PA 设备补齐字段清单 | ADR-0017 |
| D-10 | **合同已闭（M2 签名定稿）** | 连续 + 离散 Batch、跨组独立缓冲、容量/块几何查询、越界/空选择整体拒绝、`push` 两阶段读与状态机规则已定；M2 产出 `uss.h` 完整签名与错误码表 | ADR-0010 / 0018 / 0019 |
| D-11 | **模型已闭（M2 字段定稿）** | 文件内轻量 `Region` + M:N 引用与文件内复检引用已定；M2 固化精确字段名与校验样例 | ADR-0016 / 0017 |
| D-12 | **首版已闭 / M4 Python 后置** | C++20 核心 + 纯 C11 ABI + 静态自包含单库 + 首版 `.NET`（`net10.0`/`net48`）+ `1.0` `abidiff` 门禁已定（Linux 先闭环、Windows M3 实测）；Python 绑定延后至 M4 | ADR-0020 |
| D-13 | **明确后置** | 混合扫描（单晶与阵列/PA 与 FMC 同文件或同 Scan）与多独立运动探头位置模型 | ADR-0017 |
| D-14 | **明确后置** | HMC/PWI/Sparse 部分收发对矩阵声明与跨组异构矩阵（`FMC` 首版亦仅留预留口） | ADR-0009 / 0017 |
| D-15 | **已关闭** | 段内暂停同 Scan；封存或干净关闭后不支持重开追加原始波形 | ADR-0016 |
| D-16 | **模型已闭（M2 wire 定稿）** | 统一快照模型 + Write-Once 旁路容器（强绑定 UUID/ScanID，临时文件 + 原子 `rename` 替换）已定；M2 固化快照与 `EndStatus` 精确 wire 编码 | ADR-0016 / 0017 |
| D-17 | **独立扩展层（M4）** | 旁路 3D 空间索引与可插拔多回波代表选择（只消费 Core 只读 API，不阻塞 Core M3） | ADR-0016 |
| D-18 | **独立扩展层（M4）** | 窗口选峰扩展（前沿成对输出位置/时间与幅值，等用户算法参考，不阻塞 Core M3） | ADR-0016 |
| D-19 | **明确后置** | 多文件组织、跨文件扫描与跨文件复检引用（定案前由 UMS 持有） | ADR-0015 / 0016 |

<a id="closure-gates"></a>
### 待定项的阶段闭合门槛

推进里程碑状态统一维护于 [SPEC_TEST_PLAN.md](SPEC_TEST_PLAN.md#milestones)：

| 阶段 | 须闭合的 D 项与硬性证据 |
|---|---|
| **M2（格式与 ABI 冻结前）** | 补齐 `D-02`/`D-09` 真实设备字段与上限事实；产出无 `TBD` 的 HDF5 wire 规范（`D-01`/`D-07`/`D-11`/`D-16`）与 C11 头文件/错误码/状态表（`D-08`/`D-10`）；完成单 Scan 多级块索引（数千块）的 `MAP-02 + SWMR` SIGKILL 验证（`D-05`）；通过独立 1.14 读取器互读样例（`T-22`/`UC-27`） |
| **M3（Core 首版验收）** | 完成 C++20 核心、静态自包含单库、Linux x64 + Windows 10+ MSVC 与 `.NET`（`net10.0`/`net48`）绑定验收（`D-12`）；完成真实波形默认块尺寸/压缩校准（`D-03`/`D-04`）、>100 GB 超 RAM 与故障恢复门禁 |
| **M4（扩展与后续）** | 独立扩展层（`D-17`/`D-18`）、官方 Python 绑定（`D-12` 后置项）、可选 GPU `nvCOMP` 解压（`D-06`）；`FeatureOnly`/`FMC` 细化及 `D-13`/`D-14`/`D-19` 按需演进 |

## 11. 契约修订流程

按“候选规则 → 正反样例 → 独立检查 → 修订契约”迭代；变更须注明需求依据、数据影响与旧实验适用性，理由写入 `docs/decisions/`（[ADR-0007](decisions/0007-documentation-structure.md)）。禁止在测试代码或外部文档维护隐含第二套规范。
