# 访问场景映射与 Spec 验证计划

状态：已依据 [ADR-0001～ADR-0021](decisions/README.md) 完成 Core 首版定型与减痛重构（去 SWMR + 外部 `.wal` + 锁外并发读 + 极简 `push`-only ABI + `CellCoord` 排序索引）；本轮不修改或重跑既往代码/实验，产品 `UC` 与 `T` 均未执行，M1 test-only 证据仅保留其原适用范围。

总体边界见 [DESIGN.md](DESIGN.md)，唯一数据与存储契约见 [DATA_SPEC.md](DATA_SPEC.md)，首版工程合同见 [SDK_CONTRACT.md](SDK_CONTRACT.md)，磁盘编码见 [WIRE_FORMAT.md](WIRE_FORMAT.md)，场景与历史基准局限见 [SCENARIO_AUDIT.md](SCENARIO_AUDIT.md)。按 [ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)，测试报告状态机（`PASS`/`FAIL`/`NOT_RUN`/`BLOCKED`/`UNSUPPORTED`）仅属测试套件，不耦合进运行时库。

## 1. 分离验证目标与消费场景分工

### 1.1 四类分离验证目标

| 类型 | 目标 | 当前边界 |
|---|---|---|
| 符合性 | 验证语义、结构、关联和拒绝行为 | 先用小型、逐项可核对的独立期望样例推进 |
| 规模/性能 | 验证 `O(1)` 打开、有界内存、锁外多 Reader 并发、持续写入及 `CellCoord` `O(log N)` 查回 | 数值目标仍待 `D-02`/`D-03` 实机事实输入；不能替代符合性 |
| 故障恢复 | 验证非 SWMR + 外部 `.wal` + 低频 `fsync` + 独立恢复子进程隔离恢复（含 EA `>=20,000` 块） | 高频 Flush 保进程崩溃，低频 `complete_scan`/`seal`/旁路强制 `fsync` |
| 可选加速 | 验证 M4 GPU `nvCOMP` 完整编码链解码一致与端到端收益 | 非 Core M3 必选 |

<a id="access-mapping"></a>
### 1.2 访问场景分层与 `UC` 追踪

读取覆盖文件中保存的全部超声内容（[BUS-01](DATA_SPEC.md#bus-01)），五类重点场景通过可配置 `(F_chunk, K_chunk, S)` 波形分块、大块解耦 `frames/meta`（`F_meta_chunk`）与 `frames/cell_index` 排序索引兼顾（离散帧清单于 v0.2 增量追加）：

| 消费场景域 | 核心请求与交付重点（规则见 `DATA_SPEC` / `SDK_CONTRACT`） | 追踪入口 |
|---|---|---|
| 中立容器、多 Scan 独立与严格生命周期 | 枚举 UUID / 轻量 M:N `Region` / 逻辑拼接组 `ScanGroup` / `Scan`；支持 `cancel_empty_scan`；拒 0 帧完成与 0-Scan 封存；`LIF-02` 独立子进程原地恢复 | UC-17、UC-19；T-12/T-15 |
| 多区域拼接与多目标/跨文件复检引线 | 文件内 M:N `Region`、`ScanGroup`、多目标 `reinspection_targets[]`（含可选跨文件 `target_file_uuid` 与 `continuation_of_file_uuid`；多文件引擎归 `D-19`） | UC-18（多文件联合 BLOCKED） |
| 单晶异构与上层帧内选择 | 跨组保留各自 `τ_g`/`S_g`/`SignalDescriptor`；Core 交付每组稠密 `push`，帧内选择由上层纯内存核对保序保重复；越界与空选择整体拒绝 | UC-01～05 |
| PA 完整帧、DMA 双阵与无定位读取 | 一帧共用唯一 `P_n`，`pos_valid` + 编码器逐轴有效掩码、姿态约定、`crs_transforms` 与同步等级 | UC-06～08、UC-21 |
| FMC 矩阵（预留模式） | 显式 π、配对不展开、互易对独立、异构不强转 | UC-09～13（FMC 归 M4） |
| `push` Batch、`staging_budget` 与超 RAM | 连续 `(start, count)` `push`（离散清单 v0.2）；每组独立稠密缓冲；`staging_budget` 原子性与两遍/流式标志；`O(1)` 打开与块对齐 `Batch-of-SoA` | UC-14；T-06/T-14/T-18 |
| 有效全 0 / 无效零填充 / 重复位置 | LSB-first packed bitset 区分有效全 0 与 `valid=0` 零填充；不合并重复位置帧 | UC-15、UC-16 |
| 全波、按 Scan 伴生快照与版本化旁路 | Core 首版聚焦 `full_wave` + `FileOpen` 态多次追加 1..N Scan 伴生快照（共享/按层状态与来源）+ 版本化 Write-Once 旁路文件与原子指针切换；`wave_and_feature`/`FeatureOnly` 归 M4 | UC-20、UC-24 |
| 分模式 Schema、`CellCoord` 排序索引与外部互通 | C11 强类型最小解码核 + ASTM E2339/E2663（含水浸/2D-TCG/PCS）可选物理表 + `VendorExtension`；`frames/cell_index` `O(log N)` 查回 `0~N` 帧与四类子集；外部经 C11 创建并由 SDK 独立核验 | UC-22、UC-26、UC-27；T-21/T-22 |
| **M4 独立可选扩展层（不阻塞 Core）** | 3D 旁路空间索引与可插拔多回波选择（`D-17`）；窗口选峰峰峰值与前沿成对输出（`D-18`） | UC-23、UC-25（BLOCKED，归 M4） |

- **TFM 与离线算法消费边界**：离线重建/TFM 消费连续 `push` 块后在内存中按逐对选样表取样；稠密形状不代表共同物理时间轴；算法须连同有效性位图消费样本；派生结果绝不改写原始文件。

## 2. 小型样例策略

首轮使用容易逐项核对的小数据，不追求吞吐：各 Frame 和流样本可区分，基础正例显式提交 `valid=1`，变体覆盖 `valid=0`、有效全 0、重复位置、`pos_valid=0`、编码器单轴无效与 `f32` 按位保真；损坏样例在隔离目录生成。

流组划分：`H` 三条异构流各自独占 `K_g=1`；`P` 三个声束为 `K_g=3` PA 声束集；`F` 九个收发对（预留）；`W` 四个单晶 Scan 各一组。

<a id="semantic-fixtures"></a>
### 2.1 异构单晶样例 H

| 流 | dtype / 长度 | Frame 0 | Frame 1 |
|---|---|---|---|
| W0 | u8 / 4 | `[0,127,128,255]` | `[1,126,129,254]` |
| W1 | u16 / 3 | `[0,256,65535]` | `[1,257,65534]` |
| W2 | i32 / 5 | `[-2147483648,-1,0,65536,2147483647]` | `[-2147483647,-2,1,65537,2147483646]` |

另配 `f32` 变体覆盖 `-0.0` 与自定义 `NaN` payload 按位无损保真，以及 `msb` 左对齐移位掩码与 `log_db` 换算验例（[WIRE_FORMAT.md §6.2](WIRE_FORMAT.md#scan-schemas)）。

### 2.2 常规 PA 样例 P

两个 Frame、三个声束、每波形八点、测试 dtype `u16`：`W[n,b,s] = 1000*n + 100*b + s`。每帧共享唯一编码器位置 `P_n`（含 `pos_valid`、逐轴掩码 `pos_axis_valid_mask` 与同步等级）+ `CellCoord` + `nullable` 理论坐标列与 `pass_index` 列（打包入 `frames/meta`）。`P0=P1` 变体两帧不合并；固定几何、`crs_transforms` 与法则 `L0/L1/L2` 各定义一次。

### 2.3 FMC 样例 F（首版模式预留，保留语义基线）

两个 Frame、三个 Tx、三个 Rx、八样本，`X[n,i,j,s] = 1000*n + 100*i + 10*j + s`；保留 `FMC-01` 五类映射反例（缺口、互易别名、悬空流、Tx 冲突、Rx 冲突）与逐对选样表 `Q` 期望，留待 M4 启用。

<a id="uc-regression"></a>
### 2.4 最小 UC 回归集

以下全部未执行：**`UC-18`（多文件联合部分）、`UC-23`、`UC-25` 为 `BLOCKED`（归 M4，不阻塞 Core）；`UC-09～13`（FMC）及 `UC-20` 中的 `wave_and_feature`/`FeatureOnly` 归 M4；其余为 Core M3 `NOT_RUN`。**

| 用例 | 归属层 / 阶段 | 样例与请求 | 独立预期 / 拒绝条件 | 规则追踪 |
|---|---|---|---|---|
| UC-01 | Core M3 | H/P 分别解释；类别冲突反例 | 模式 Schema 明确区分，不靠 shape 猜测 | U-01/U-03 |
| UC-02 | Core M3 | 同 Scan 重复固定方案；尝试变更长度/dtype/采样轴 | 固定定义复用，真实变更被旧 Scan 拒绝 | U-02/U-04 |
| UC-03 | Core M3 | H 三个异构流组联合 `push` 回读（含 `f32` `NaN`/`-0.0` 与 `msb` 对齐变体） | 与 2.1 样本、符号、dtype、按位及标度解释一致 | U-04 |
| UC-04 | Core M3 | 同 shape/dtype 的阵元接收与 PA 合成输出 | `data_level` 明确可辨识，不互换解释 | U-03/U-04 |
| UC-05 | Core M3 | H′（Frame 0 的 W0 `valid=0`）`push` 回读与上层流选择 | 有效位图与零填充一致，无效不跳过，关联正确 | U-08/U-09/U-10 |
| UC-06 | Core M3 | P 完整帧与多束读取（含 DMA 双阵 `tx_probe_id != rx_probe_id` 变体） | 一帧一唯一原始位置 `P_n`，不新增逐束原始位置 | U-05 |
| UC-07 | Core M3 | P `push` 回读与上层束 `[2,0,2]` / 样本 `[1,4)` 核对 | 数值与 `P1/L2、L0、L2` 一致 | U-03/U-05/U-10 |
| UC-08 | Core M3 | 不定位读 P；派生束位置覆盖 `P_n` 反例 | 原始读取成立，拒绝覆盖 `P_n` | U-05/U-12 |
| UC-09～13 | **M4（FMC 预留）** | F 全矩阵、子矩阵、配对与 Q 表 | 留待 M4 展开 `FMC` 模式时启用 | U-06/U-07；FMC-01/02 |
| UC-14 | Core M3 | P 连续 `push` 读、容量/布局查询、`staging_budget` 边界与超 2 GiB 非托管缓冲（离散清单 v0.2） | `staging_budget` 内损坏目标逐字节不变；超预算默认拒或按显式两遍/流式标志执行；Reader 关闭后缓冲仍可用 | U-11；READ-03/BUF-01 |
| UC-15 | Core M3 | 有效全 0/非零、无效省略、LSB-first 尾部位非零、位图缺失、损坏反例 | 真实全 0 保真、无效零填充；缺失或尾部位错整批拒；损坏不转无效位 | U-08/U-12 |
| UC-16 | Core M3 | 重复位置不同帧；封存后关闭重开重放 | 不合并帧，结果不变，源文件不改写 | U-10/U-12 |
| UC-17 | Core M3 | 2.5 W 四个 Scan（局部 `n/k` 重复、跨 Scan 异构）与 `ScanGroup` | 中立容器独立枚举/读取，拼接组显式可辨识但不隐式融合原始波形 | U-03/U-04/U-13/U-14；SCAN-01 |
| UC-18 | Core M3 / 后置 | 轻量 M:N `Region`、`ScanGroup`、多目标 `reinspection_targets[]`（含可选跨文件 `target_file_uuid`）；多文件联合引擎（**BLOCKED** 待 `D-19`） | 拒文件内悬空引用；跨文件仅保元数据引线 | REL-01/SCAN-02、D-11/D-19 |
| UC-19 | Core M3 | 顺序完成 W 各 Scan、`cancel_empty_scan(N==0)`、封存及空 Scan/空壳/非法追加反例 | `N==0` 可经 `cancel_empty_scan` 回退并正常封存先序 Scan；拒 0 帧完成与 0-Scan 封存；合法保留空 `Region` | U-12/U-13；LIF-01/02 |
| UC-20 | Core M3 / M4 | Core M3 验 `full_wave` + `EndStatus`/空 `Region`；`wave_and_feature`（流式特征）与 `FeatureOnly` 归 **M4** | 按保留交付，缺口如实表达，不虚构波形 | RET-01 |
| UC-21 | Core M3 | 无位置、`pos_valid=0` 保全有效波形、`ENCODER_I64` 单轴有效掩码、姿态约定、`CellCoord` 排序索引 `O(log N)` 查回与大块 `frames/meta` | 波形保全，不靠 `NaN` 猜无效，有效单轴不因未接轴丢失，`CellCoord` 精确返回 `0~N` 帧 | POS-01/02、D-01 |
| UC-22 | Core M3 | 单晶/PA 强类型必填核 + ASTM E2339/E2663 可选物理表（含水浸/2D-TCG/PCS）+ `crs_transforms` + 参数化几何 + `VendorExtension` | 脱离 UMS/DB 完整自解释，可选物理表宽容 JSON Schema 校验 | REL-01、D-09 |
| UC-23 | **扩展层 M4** | 3D 旁路空间索引与可插拔多回波代表选择 | **BLOCKED**：归 M4（不阻塞 Core M3） | ACCESS-01、D-17 |
| UC-24 | Core M3 | `FileOpen` 态按 Scan 多次追加伴生快照（1..N Scan、按层 `status`/`source`）；封存后拒原地改写；离线版本化旁路容器 + 原子指针切换（含 Windows 边看边重算） | 读不重算、来源不变；Windows 旧 Reader 打开期间重算写新版本与切指针无共享锁冲突且失败保旧 | SNAP-01、LIF-01、D-16 |
| UC-25 | **扩展层 M4** | 独立选峰扩展：窗口峰峰值与前沿位置/时间+幅值 | **BLOCKED**：归 M4（不阻塞 Core M3） | MEAS-01、D-18 |
| UC-26 | Core M3 | Core 规范数据子集（Scan / `CellCoord` 区域 / 通道声束 / 样本窗口） | 保留解释、状态与来源；不附带导出打包 | ACCESS-01、D-11 |
| UC-27 | Core M3 | **跨系统外部创建与完整读取**：外部系统经极简 C11 ABI 创建文件，第三方不依赖 UMS/DB 凭 SDK（含独立只读 `uss_verify_file`）完整互读与自解释 | 验证 `ADR-0015～0021` 跨系统交付与自包含解释闭环 | BUS-01、ID-01、R-20；D-07/D-09 |

<a id="multi-scan-fixture"></a>
### 2.5 多 Scan 容器样例 W

四个单晶 Scan（`A/B/C/D`，各 `N=2`，局部流均名 `k0`：`A/B/C` `u16/3`，`D` `u8/4`），`A/B/C` 归入同一逻辑拼接组 `ScanGroup`，`D` 作为独立复检 Scan 引用 `A/B`。验证跨 Scan `n/k` 不冲突、`cancel_empty_scan()` 安全取消中间空 Scan、拒绝 0 帧完成与 0-Scan 封存、拒绝向已完成/已封存文件追加。

## 3. 需求—规则—用例追踪

除 `T-08` 为 **SUPERSEDED** 外，以下活动项全部 **`NOT_RUN`**。

| 用例 | 需求 | Spec 规则 | 样例/操作与预期 | 依赖与边界 |
|---|---|---|---|---|
| T-01 | [R-01](DESIGN.md#r-01)、[R-11](DESIGN.md#r-11) | [DOC-01](DATA_SPEC.md#doc-01)、[ID-01](DATA_SPEC.md#id-01)、[VAL-01](DATA_SPEC.md#val-01) | 已知/未知 `format_major`、容器角色、UUID、模式 Schema 与 `required_features` 拒绝规则 | `WIRE_FORMAT` r2 |
| T-02 | [R-02](DESIGN.md#r-02)、[R-03](DESIGN.md#r-03) | [REC-01](DATA_SPEC.md#rec-01)、[MAP-01](DATA_SPEC.md#map-01)、[WRT-01](DATA_SPEC.md#wrt-01) | H/P 同步写入与连续 `push` 读，`(F,K,S)` + `F_meta_chunk` 关联一致 | UC-01/05/06/14 |
| T-03 | [R-05](DESIGN.md#r-05) | [WAV-01](DATA_SPEC.md#wav-01)、[WAV-02](DATA_SPEC.md#wav-02) | 有效缺波形、`S_k±1`/错 dtype（拒 `f64`/复数）/错位图整批拒绝 | UC-02/03/15 |
| T-04 | [R-02](DESIGN.md#r-02)、[R-05](DESIGN.md#r-05) | [WAV-01](DATA_SPEC.md#wav-01)、[WAV-02](DATA_SPEC.md#wav-02) | 整数 `{i8..u32}`、`f32`（`NaN` payload / `-0.0`）按位保真与 `msb`/`log_db` 标度一致 | UC-03/04 |
| T-05 | [R-05](DESIGN.md#r-05) | [STA-01](DATA_SPEC.md#sta-01) | LSB-first packed bitset、尾部位清零校验、有效全 0 保真、`valid=0` 零填充与严格模式 | UC-15 |
| T-06 | [R-04](DESIGN.md#r-04) | [READ-01/03](DATA_SPEC.md#read-01)、[BUF-01](DATA_SPEC.md#buf-01)、[META-01](DATA_SPEC.md#meta-01) | 单一 `push` 原语、容量查询、`staging_budget` 边界、`.NET` `SafeHandle` 与超 2 GiB 非托管缓冲 | UC-05/07/14/15 |
| T-07 | [R-03](DESIGN.md#r-03)、[R-04](DESIGN.md#r-04) | [POS-01/02](DATA_SPEC.md#pos-01)、[PA-01](DATA_SPEC.md#pa-01)、[ID-02](DATA_SPEC.md#id-02) | 大块 `frames/meta`、`pos_valid`、编码器逐轴有效掩码、姿态约定、`CellCoord` 排序索引 `O(log N)` 与标准附加列 | UC-06～08/16/17/21 |
| T-08 | [R-11](DESIGN.md#r-11) | [PAR-02](DATA_SPEC.md#par-02) | 旧动态快照与 offsets 用例（SUPERSEDED） | — |
| T-09 | [R-02](DESIGN.md#r-02)、[R-11](DESIGN.md#r-11) | [WAV-01](DATA_SPEC.md#wav-01)、[PAR-01](DATA_SPEC.md#par-01) | 定义真实变更被旧 Scan 拒绝；预定程序循环允许 | UC-02 |
| T-10 | [R-04](DESIGN.md#r-04) | [READ-01](DATA_SPEC.md#read-01)、[READ-02](DATA_SPEC.md#read-02) | 空选择、帧越界与目标缓冲不足整体拒绝（离散清单 v0.2） | UC-14 |
| T-11 | [R-02](DESIGN.md#r-02)、[R-07](DESIGN.md#r-07) | [REC-02](DATA_SPEC.md#rec-02)、[WRT-02](DATA_SPEC.md#wrt-02)、[LIF-01](DATA_SPEC.md#lif-01) | `E_x>N` 不暴露、`E_x<N`/`stored_xxh3` 不符报错；双槽 `commit` 优先于未同步 `/lifecycle` 且双槽全毁判不可恢复 | 逐 Scan 检查 |
| T-12 | [R-07](DESIGN.md#r-07) | [LIF-01](DATA_SPEC.md#lif-01)、[SNAP-01](DATA_SPEC.md#snap-01) | 顺序完成、`cancel_empty_scan(N==0)`、按 Scan 多次追加伴生快照、`seal` 含 `fsync` 与删 `.wal`、Windows 版本化旁路指针边看边替换 | UC-19/24 |
| T-13 | [R-03](DESIGN.md#r-03)、[R-05](DESIGN.md#r-05) | [WRT-01](DATA_SPEC.md#wrt-01) | 批次中间含非法输入整批拒绝，前缀不变且返回 `NOT_COMMITTED` | 前置校验原子性 |
| T-14 | [R-06](DESIGN.md#r-06)、[R-15](DESIGN.md#r-15) | [IO-01](DATA_SPEC.md#io-01)、[WRT-01/03](DATA_SPEC.md#wrt-01)、[BUF-01](DATA_SPEC.md#buf-01)、U-15 | `push` 在 `staging_budget` 内损坏目标不变、超预算按显式标志行为一致；写失败禁重试禁补写未 Flush 尾部、禁降级已完成 Scan、禁封存 0-Scan 空壳 | 详见 3.1 |
| T-15 | [R-06](DESIGN.md#r-06)、[R-08](DESIGN.md#r-08) | [WRT-03](DATA_SPEC.md#wrt-03)、[MAP-02](DATA_SPEC.md#map-02)、[LIF-02](DATA_SPEC.md#lif-02)、U-15 | **非 SWMR + 外部 `.wal` + Extensible Array `>=20,000` 块 + dense group + 大快照** 随机 SIGKILL，独立恢复子进程原地只读（含 `EOA>EOF` 修补 VFD）验通 `stored_xxh3` 且源文件哈希不变 | `D-05` 核心门禁 |
| T-16 | [R-10](DESIGN.md#r-10) | [ID-02](DATA_SPEC.md#id-02)、[CMP-01](DATA_SPEC.md#cmp-01) | 未知 filter、外部 `HDF5_PLUGIN_PATH` 劫持屏蔽与不支持参数明确拒绝 | — |
| T-17 | [R-05](DESIGN.md#r-05)、[R-10](DESIGN.md#r-10) | [CMP-01](DATA_SPEC.md#cmp-01)、[WAV-02](DATA_SPEC.md#wav-02) | `none`、`shuffle+zstd`、`shuffle+lz4`（含单块 `<=1 GiB`）回读逐值一致 | 覆盖尾块与非整 `K_chunk` |
| T-18 | [R-09](DESIGN.md#r-09) | [CAP-01](DATA_SPEC.md#cap-01)、[REC-02](DATA_SPEC.md#rec-02) | 超 100 GB、工作集超 RAM、`O(1)` 打开、`CellCoord` `O(log N)` 毫秒点查与块对齐 `push` 流式读写 | D-02/D-03 |
| T-19 | [R-09](DESIGN.md#r-09) | [REC-02](DATA_SPEC.md#rec-02)、[CAP-01](DATA_SPEC.md#cap-01) | 32 位边界与 u64 极值防溢出、单 Frame/单条带超限拒绝 | 单元测试与模拟元数据 |
| T-20 | [R-10](DESIGN.md#r-10) | [CMP-02](DATA_SPEC.md#cmp-02)、[WAV-02](DATA_SPEC.md#wav-02) | GPU `nvCOMP` 完整解码一致与端到端对比 | D-06；可选 M4 |
| T-21 | [R-11](DESIGN.md#r-11)、[R-13](DESIGN.md#r-13) | [META-01](DATA_SPEC.md#meta-01)、[ID-02](DATA_SPEC.md#id-02)、[REL-01](DATA_SPEC.md#rel-01)、[VAL-01](DATA_SPEC.md#val-01) | 强类型最小解码核 + ASTM E2339/E2663 可选物理表（水浸/2D-TCG/PCS）+ `crs_transforms` + 参数化几何核对 | UC-22、D-09 |
| T-22 | [R-01](DESIGN.md#r-01)、[R-04](DESIGN.md#r-04)、[R-20](DESIGN.md#r-20) | [BUS-01](DATA_SPEC.md#bus-01)、[DOC-01](DATA_SPEC.md#doc-01)、[ID-01](DATA_SPEC.md#id-01)、[VAL-01](DATA_SPEC.md#val-01) | 不依赖 UMS/DB，经极简 C11 ABI 外部创建并凭独立只读 `uss_verify_file` 与跨系统 SDK 读取器完整自解释与拒未知必要能力 | UC-27（已取消 1.14 双实现门禁） |
| T-23 | [R-01](DESIGN.md#r-01)、[R-12](DESIGN.md#r-12) | [SCAN-01/02](DATA_SPEC.md#scan-01)、[READ-01](DATA_SPEC.md#read-01)、U-14 | W 多 Scan、轻量 M:N `Region`、`ScanGroup` 逻辑拼接与多目标/跨文件复检引线 | UC-17/18/19 |
| T-24 | [R-14](DESIGN.md#r-14) | [CORE-01](DATA_SPEC.md#core-01)、[BUF-01](DATA_SPEC.md#buf-01)、U-16 | 锁外并发 `pread`/`ReadFile` 多 Reader 吞吐、慢盘不阻塞本地盘/GC Finalizer、OS 文件 ID + `F_OFD_SETLK`/`LockFileEx` 哨兵锁（含禁用 `HDF5_USE_FILE_LOCKING`）、Windows 中文路径与 `H5dont_atexit` 退出无死锁 | Linux + Windows M2/M3 |

<a id="risk-verification"></a>
### 3.1 M2 薄垂直切片优先取证（含 Windows 前移）与 M3 完整覆盖

| 现有追踪 | M2 薄垂直切片优先取证 | M3 完整覆盖与限制 |
|---|---|---|
| T-15 EA `>=20,000` 块崩溃隔离 | **核心门禁**：非 SWMR + 外部 `.wal` + Extensible Array 二级分页（`>=20,000` 块）+ dense group（`>=100` 对象）+ 大快照写入下随机 SIGKILL，经独立恢复子进程（修补 VFD 覆盖 `EOA>EOF`）原地验通且源文件哈希不变 | 覆盖追加/Flush/取消空 Scan/完成/快照/封存全阶段故障点 |
| T-24 Windows + `.NET 4.8` 烟雾闭环 | **前移至 M2**：Windows MSVC `/MT` 静态单库构建、非 ASCII 中文路径、`H5dont_atexit()` 退出无死锁、`LockFileEx` 哨兵锁、`.NET 4.8` P/Invoke 烟雾读写 | 补齐 Linux 低 `glibc` 发行容器、`readelf`/`dumpbin` 符号门禁、多核锁外 `pread` 扩展性与 `.NET 10` 联调 |
| T-12 / T-14 生命周期与暂存边界 | `cancel_empty_scan(N==0)`、禁补写未 Flush 尾部、`staging_budget` 原子读与超预算标志、Windows 版本化旁路快照边看边切换 | 覆盖延迟 I/O 错、`seal_with_failure` 与带失败标记重开 |
| T-07 / T-18 大块帧元与 `CellCoord` | `frames/meta` 大块解耦与 `frames/cell_index` `O(log N)` 百 GB 级查回耗时、`O(1)` 冷开内存 | 超 100 GB 超 RAM 块对齐 `Batch-of-SoA` 全链路峰值预算与默认值校准 |

## 4. 场景证据转验证与独立核验器

<a id="scenario-validation"></a>
算法输出与存储符合性分开验证；运行时核验由 SDK 独立只读 `uss_verify_file()`（有界 O(1) 内存流式扫描全部对象与 `stored_xxh3`）提供，不与离线测试报告耦合。性能测量保留 `none` 对照、固定输入比较 `(F_chunk, K_chunk, S)`、区分冷/热页缓存并记录完整环境与版本（历史局限见 [SCENARIO_AUDIT.md#historical-benchmark-limits](SCENARIO_AUDIT.md#historical-benchmark-limits)）。

<a id="milestones"></a>
## 5. 推进里程碑与 Core 首版验收门禁

| 里程碑 | 交付物 | 完成判据 | 当前状态 |
|---|---|---|---|
| **M0** | 需求收敛、数据契约与减痛重构定型 | 确立两层架构、非 SWMR + 外部 `.wal`、锁外并发读、极简 `push`-only ABI、拼接/复检与超声领域修复（`ADR-0001～0021`） | **已完成定型**；停止扩写文档，转入代码驱动薄切片 |
| **M1** | 历史局部机制原型与进程崩溃探针 | 取得旧版单 PA 流组写入保护、无 `fsync` 进程崩溃初步证据 | **历史局部实验完成**（[M1 报告](../experiments/m1/REPORT.md)，不重跑、不替代产品验收） |
| **M2** | **极简 `uss.h` + 代码驱动薄垂直切片（含 Windows + `.NET 4.8` 前移）** | 起草极简 `uss.h`；构建 Linux + Windows MSVC 静态单库与 `.NET 4.8` 烟雾调用；完成非 SWMR + 外部 `.wal` + EA `>=20,000` 块 SIGKILL 独立子进程恢复（`D-05`）与锁外 `pread` 验证；补齐 `D-02`/`D-09` 实机样本 | **下一阶段（立即启动）** |
| **M3** | **SDK Core 首版实现与全面验收** | 完整单晶/PA 全波、`ScanGroup`、排序 `CellCoord` 索引、按 Scan 伴生与版本化旁路快照、`.NET`（`net10.0`/`net48`）完整绑定、>100 GB 超 RAM 与故障恢复门禁；`1.0-rc` 启用 `SONAME`/`abidiff` 门禁 | 未执行 |
| **M4** | **独立扩展层、流式特征、Python 绑定与 GPU 加速** | `wave_and_feature`（流式硬件特征与选择性留波）、`FeatureOnly`、`FMC`、3D 旁路索引/多回波（`D-17`）、窗口选峰（`D-18`）、官方 Python 绑定、GPU `nvCOMP`（`D-06`） | 未执行；**不阻塞 Core M3** |

<a id="core-acceptance"></a>
### Core 首版（M3）验收门禁

本门禁对应 **SDK Core 首版（单晶 + 相控阵全波 + 伴生/版本化旁路快照，极简 `push`-only C11 ABI + `.NET`）**；`wave_and_feature`/`FeatureOnly`/`FMC`、离散帧清单（v0.2）、独立扩展层（`UC-23`/`UC-25`）、Python 官方绑定与 GPU 解压均不阻塞 Core M3 通过。

| 验收面 | 通过所需证据 | 复用追踪 |
|---|---|---|
| 数据、模式与拼接/复检 | `H/P/W`（含 `f32` 按位、`msb`/`log_db`、编码器逐轴掩码、姿态约定、`crs_transforms`）、单晶/PA 独立 Schema + E2663 水浸/2D-TCG 物理表、`Region`/`ScanGroup`/`reinspection_targets[]` 与 `CellCoord` 排序索引正确 | UC-01～08/14～22/26、T-02～11/T-21/T-23 |
| 输入、越界与容量拒绝 | 非法批次修改前拒绝（`NOT_COMMITTED`）；空选择、越界与容量不足整体拒绝；u64 溢出与单 Frame/条带超限显式报错 | T-03/T-10/T-13/T-19 |
| 原子性、锁与并发读 | `push` `staging_budget` 原子性；锁外并发 `pread`/`ReadFile` 多核扩展且不阻塞 `.NET` GC Finalizer；OS 文件 ID + `F_OFD_SETLK`/`LockFileEx` 哨兵锁跨进程生效 | T-06/T-14/T-24、UC-14 |
| 生命周期、快照与子进程恢复 | `cancel_empty_scan(N==0)`、拒 0 帧完成与 0-Scan 封存；按 Scan 多次追加 1..N Scan/按层伴生快照；Windows 版本化旁路指针边看边替换；非 SWMR + 外部 `.wal` + EA `>=20,000` 块 SIGKILL 独立子进程原地恢复（源文件哈希不变） | T-12/T-14/T-15、UC-19/24 |
| 编解码与跨系统自解释 | `none`/`shuffle+zstd`/`shuffle+lz4` 逐值一致（屏蔽 `HDF5_PLUGIN_PATH` 劫持）；经 C11 ABI 外部创建并凭独立只读 `uss_verify_file` 完整互读与拒未知必要能力 | T-01/T-16/T-17/T-22、UC-27 |
| 静态单库与 `.NET` 绑定 | Linux 低 `glibc` + Windows MSVC `/MT` 静态自包含单库（隐藏内部符号、`H5dont_atexit`、中文路径）；`.NET 10` & `.NET 4.8` `SafeHandle` + >2 GiB 非托管 `push`；`1.0-rc` 启用 `SONAME`/`abidiff` 门禁 | T-06/T-14/T-24；`SDK_CONTRACT.md` |
| 规模与负载 | 超 100 GB 且工作集超 RAM、`O(1)` 打开、`CellCoord` `O(log N)` 毫秒点查；全链路峰值预算与块对齐 `Batch-of-SoA` 负载达标 | T-18/T-19；D-02/D-03/D-04 |
