# 剩余开放项与 M2 薄切片推进清单

状态：已依据 [ADR-0001～ADR-0021](decisions/README.md) 完成 Core 首版定型与减痛重构；本文遵循 [ADR-0007](decisions/0007-documentation-structure.md) 仅维护**尚未闭合的实机事实输入、M2 薄切片任务与 v0.2/M4 后置项**。唯一 `D-01`–`D-19` 权威状态总表见 [DATA_SPEC.md](DATA_SPEC.md#open-items)，工程合同见 [SDK_CONTRACT.md](SDK_CONTRACT.md)，二进制布局草案见 [WIRE_FORMAT.md](WIRE_FORMAT.md)。

---

## 1. 已定型决策速查（不再重复展开）

| 主题域 | 闭合结论摘要 | 权威 ADR / 合同 |
|---|---|---|
| 模型基线（`Q1–Q7`、`D-15`） | 两层架构、中立容器 UUID、分模式独立 Schema、解除 `h5py` 裸读、Write-Once 封存、关闭 `D-15` | [ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md) |
| 首版范围、拼接与复检（`D-03/04/09/11/16`） | 首版单晶/PA 全波 + 伴生/版本化旁路快照（`wave_and_feature`/`FeatureOnly`/`FMC` 归 M4）；轻量 M:N `Region` + 逻辑拼接组 `ScanGroup` + 多目标/可选跨文件复检引线；1..N Scan/多次追加/按层状态来源快照；强类型 C11 最小解码核 + ASTM E2339/E2663（含水浸/2D-TCG/PCS）宽容 JSON 物理表 + `crs_transforms` | [ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md) |
| 减痛存储引擎与故障隔离（`D-05/10`） | 保留 HDF5 容器壳但**砍按 Scan SWMR** + **外部临时 `.wal`**（封存删）+ **单一 `stored_xxh3`** + **`O(1)` 打开** + **只读 I/O 移出全局锁** + **低频 `fsync`** + **`LIF-02` 独立恢复子进程隔离** + `cancel_empty_scan()` 修复 `N==0` 死锁 | [ADR-0018](decisions/0018-storage-engine-swmr-and-strict-lifecycle.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md) |
| <a id="angle-15"></a>极简 `push`-only ABI 与大块帧元（`D-01/02/04/07/08/10`，含原角度 15） | 帧元合并大块 `frames/meta`（去 `CUSTOM_STRUCT`）+ `complete_scan()` 排序 `frames/cell_index`；LSB-first 位图；`{i8..u32, f32}`；`none`/`shuffle+zstd`/`shuffle+lz4`；**砍 `poll` 与纯内存选择层**，统一连续 `push` 原语 + `staging_budget` + 布局容量查询（离散清单留 v0.2） | [ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)、[SDK_CONTRACT.md](SDK_CONTRACT.md) |
| <a id="angle-16"></a>技术栈、跨平台加固与版本（`D-07/12`，含原角度 16） | C++20 + 极简 C11 ABI 静态单库（`H5dont_atexit`/`H5PLset_loading_state(0)`/低 `glibc`/`/MT`/哨兵字节跨进程锁）；取消 1.14 独立读取器双实现门禁；首版 `.NET`（`net10.0`/`net48`）并将 **Windows + `.NET 4.8` 烟雾闭环前移至 M2**；Python 归 M4；v0.x 延后 `abidiff` 至 `1.0-rc` | [ADR-0020](decisions/0020-implementation-stack-bindings-and-versioning.md)、[ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)、[SDK_CONTRACT.md](SDK_CONTRACT.md) |

---

<a id="business-next"></a>
## 2. 立即进入 M2 代码驱动薄垂直切片前的待补输入与执行任务

> 按 [ADR-0021](decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)，本次落盘收敛后**暂停文档扩写**，直接以最小可运行代码和真实设备样本驱动后续收敛。

### 2.1 待补充的真实设备与负载事实输入（非架构分叉）

| 关联 D 项 | 所需事实输入 | 归位与作用 |
|---|---|---|
| **D-09**（实机物理字段核对） | 首批单晶与相控阵（含水浸/喷水）真实采集方案与单帧样本，用于核对可选物理表与 `SignalDescriptor` 字段完备性 | 记录入 [SCENARIO_AUDIT.md](SCENARIO_AUDIT.md)，供 `1.0` 冻结物理表 JSON Schema |
| **D-02**（规模与全链路内存预算） | 首发模式典型/最大 `K_g`、`S_g`、最大单 Frame 字节数、持续/突发写入速率，以及全链路（`Batch-of-SoA` + SDK `staging_budget` + `.NET`）峰值内存门槛 | 设定 M2/M3 上限常量与超 RAM 验收门槛 |
| **D-03 / D-04**（负载权重与实测校准） | 五类访问场景频率权重、目标主机/磁盘基准及延迟/吞吐目标 | M3 实测校准 `(F_chunk, K_chunk, S)`、`F_meta_chunk` 与 `zstd` 级别 |

### 2.2 M2 薄垂直切片核心任务（立即启动）

| 优先级 | 关联 D 项 | M2 具体交付物与闭合条件 |
|---|---|---|
| **P0（极简 C11 头文件）** | **D-10 / D-08** | 起草极简纯 C11 头文件 `include/uss.h`（~20 个核心函数：`push`-only 无 `poll`/无纯选择层、强类型最小解码核 + JSON 可选物理表、`cancel_empty_scan()`、`staging_budget`、提交状态分离与错误码表） |
| **P0（薄垂直切片 + Windows 前移）** | **D-07 / D-12** | 搭建 C++20 CMake/Ninja 静态自包含单库（非 SWMR + 外部 `.wal` + 锁外并发 `pread`/`ReadFile` + OS 文件 ID 与哨兵字节跨进程锁 + `H5dont_atexit`/`H5PLset_loading_state(0)`）及 Linux + **Windows MSVC `/MT` + `.NET 4.8` 烟雾闭环**（验证中文路径与退出无死锁），并通过 [WIRE_FORMAT.md](WIRE_FORMAT.md) `1.0-draft r2` 实测反馈反向收敛 |
| **P0（EA 大规模崩溃门禁）** | **D-05** | 执行 **Extensible Array 二级分页（`>=20,000` 块）+ dense group（`>=100` 对象）+ 大快照写入** 下的随机 `SIGKILL` 压测，验证独立恢复子进程（修补 VFD 含 `EOA > EOF`）联合 `.wal` 原地只读验通且源文件哈希不变 |

---

## 3. 渐进演进与明确后置项（不阻塞 Core M2/M3）

| 分层 | 议题与 D 项 | 现状与启动前提 |
|---|---|---|
| **Core v0.2 增量** | **离散帧清单 `frame_indices[]` 按块合并 `push`** | 待 M2/M3 连续 `push` 稳定及真实 D 扫需求验证后作为增量 C11 函数追加，不破既有 ABI |
| **M4 流式特征与预留模式** | **`wave_and_feature`（流式硬件特征与选择性留波）、`FeatureOnly`、`FMC`** | 容器枚举已预留；待单晶/PA 全波闭环后统一设计流式 `features/` 组与多态槽位状态 |
| **独立扩展层（M4）** | **3D 旁路空间索引与多回波选择（`D-17`）、窗口选峰（`D-18`）** | 仅消费 Core 只读 API；`D-18` 前沿算法判据待用户提供统一参考 |
| **绑定与加速（M4）** | **官方 Python 绑定（`D-12` 后置）、GPU `nvCOMP` 解压（`D-06`）** | 编解码与单块上限已对齐 `nvCOMP`；M4 按需交付 |
| **明确后置** | **混合扫描与多探头（`D-13`）、部分/跨组矩阵（`D-14`）、多文件联合引擎（`D-19`）** | Wire 1.0 已为跨文件复检/续扫预留轻量 `target_file_uuid` 与 `continuation_of_file_uuid` 指针，多文件联合查询后置 |
