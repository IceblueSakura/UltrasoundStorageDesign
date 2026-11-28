# ADR-0021：HDF5 减痛重构（去 SWMR + 外部 WAL + 锁外并发读）、极简 push-only ABI 与超声领域 P0 修复

- 状态：已采纳（2026-11-28）；针对批判性架构与领域评审中发现的 P0/Critical 风险，定向修订 [ADR-0004](0004-concurrency-and-borrow-scope.md)、[ADR-0005](0005-file-format-range.md)、[ADR-0006](0006-core-io-and-selection-layer.md)、[ADR-0008](0008-process-crash-scope.md)、[ADR-0017](0017-core-v1-scope-and-domain-model.md)、[ADR-0018](0018-storage-engine-swmr-and-strict-lifecycle.md)、[ADR-0019](0019-wire-encoding-and-core-io-contracts.md) 与 [ADR-0020](0020-implementation-stack-bindings-and-versioning.md) 的对应条款。
- 规则落点：[DATA_SPEC.md](../DATA_SPEC.md)、[SDK_CONTRACT.md](../SDK_CONTRACT.md)、[WIRE_FORMAT.md](../WIRE_FORMAT.md)、[SPEC_TEST_PLAN.md](../SPEC_TEST_PLAN.md)、[DESIGN.md](../DESIGN.md)、[DECISION_DIRECTIONS.md](../DECISION_DIRECTIONS.md)。
- 来源：针对 `ADR-0016～0020` 与 `WIRE_FORMAT.md 1.0-draft` 开展的多视角批判性架构/超声领域/可维护性评审及 8 项收口决策（2026-11-28）。

## 背景

在完成 `WIRE_FORMAT.md 1.0-draft` 后，从底层存储引擎、跨平台运维、C11/`.NET` ABI 安全性以及工业 UT/PAUT 领域四个视角进行的批判性复核暴露出多处结构性缺陷：
1. 保留 HDF5 同时启用按 Scan SWMR、内嵌预分配 `journal/`、全局锁内同步读盘与 1.14 独立读取器双实现，导致复杂度/收益严重倒挂（`K_chunk` 缩小触发百 MB～1 GiB 死空间、全局锁阻塞多 Reader 及 `.NET` GC Finalizer、反复关重开触发 `fcntl` 释锁竞态、宿主机内修补 VFD 存在 `EOA > EOF` 与 HDF5 CVE 崩溃风险）。
2. Core C11 ABI 承载 `poll` 与纯内存选择层在 `.NET` 下导致 `ReadOnlySpan<T>` 绕过 `borrow_generation` 产生 UAF 假象，同时大 Batch `push` 两阶段读的“有界暂存 + 单遍解码 + >2 GiB + `decoded_xxh3`”在数学上构成不可能三角。
3. 帧级微小列与波形强行共享 `F_chunk` 导致 8 字节块配 24 字节校验和（300% 膨胀）并使百 GB `CellCoord` 寻址退化为十万次随机读。
4. 领域与状态机存在 P0 断层：`wave_and_feature` 在 Wire 中无逐帧 `features/` 落盘位置；多 Scan 场景下 `ScanActive (N == 0)` 急停触发状态机死锁；快照被锁死为单 Scan/单来源/封存前写一次，无法支撑多区域拼接整件 C 扫与多闸门独立状态；Windows `MoveFileExW` 在 UMS 边看边重算时必报共享冲突；`SignalDescriptor`/`POSE_6D`/`crs_transforms`/水浸模型/多探头 2D-TCG 存在互操作歧义或缺失（另全仓 ASTM `E2738` 应为超声 `E2663`）。

## 决定

1. **HDF5 容器减痛重构（修订 `ADR-0005`/`0018`）**：
   - 保留 HDF5 作为物理容器壳（仍限定 `v1.10–v1.14` 写出格式），但**砍掉按 Scan SWMR**（Writer 全程维持单一非 SWMR 句柄，消除反复 `H5Fclose/H5Fopen` 与双恢复路径）。
   - **以独立外部临时 WAL 文件（`<file>.uss.wal`）替代内嵌 `journal/`**：Flush 仅向 `.wal` 顺序增量追加未满条带（零预分配死空间、零 Flush 重写放大），`complete_scan()` 写完尾块后重置 `.wal`，`seal()` 成功后删除 `.wal`。
   - **只读数据 I/O 移出 HDF5 全局互斥锁**：仅在全局锁内调用 `H5Dget_chunk_info_by_coord` 等纯元数据查表获取 `(file_offset, stored_size, filter_mask)`，立即释锁后经 Reader 自持独立只读 OS 句柄并发 `pread`/`ReadFile`（恢复多核 QD>1 并发与跨文件隔离，消除 `.NET` GC Finalizer 线程饥饿风险）。
   - **取消“HDF5 1.14 独立读取器双实现”强制门禁**（全员通过静态自包含单库访问，减少首版双倍实现维护债；保留 `v1.10–v1.14` 兼容写出与 SDK 自带独立只读核验器）。
2. **精简校验、低频 `fsync` 与子进程恢复隔离（修订 `ADR-0002`/`0008`/`0018`/`0019`）**：
   - 物理块**仅保留单一 `stored_xxh3`**（删除冗余的 `decoded_xxh3` 扫描与冷开 `O(N)` `sums_chain_xxh3`，实现严格 `O(1)` 打开）。
   - 高频 `flush()` 维持只交给 OS 页缓存（提供可选 `USS_FLUSH_SYNC` 标志）；**低频里程碑（`complete_scan`、`seal`、旁路快照提交）强制执行 `fsync`/`FlushFileBuffers`**（含 POSIX 目录同步），避免断电封存/替换出现 0 字节损坏文件。
   - **`LIF-02` 崩溃恢复强制在独立只读恢复子进程中执行**（联合读取 `.h5` 与 `.wal`，修补 VFD 同步处理偏移 `11` 标志、`EOA > EOF` 与跨 `[0..48)` 边界读），彻底阻断畸形 HDF5 崩垮宿主 `.NET` 进程。
3. **极简 `push`-only C11 ABI（修订 `ADR-0004`/`0006`/`0019`）**：
   - **彻底砍掉 Core C11 ABI 的 `poll` 借用状态机与 `.NET` `borrow_generation`**，全量收敛到 `push` + 块几何/容量查询（`.NET`/未来托管层按需提供基于 `push` 分配托管/池化缓冲的便利方法，彻底根治 `ReadOnlySpan<T>` UAF 假象）。
   - **合并“分析读取”与“Batch 读取”**为单一 `push` 读取原语（位置/附加列输出缓冲指针为 `NULL` 即跳过）。
   - **将纯内存帧内选择层移出 C11 存储 ABI**（不再跨 C ABI 维护保序保重复花式索引与 `Q` 表）。
   - **显式界定 `push` 原子暂存上限 `staging_budget`**（默认 64–128 MiB）：压缩块总和 `<= staging_budget` 时保证单遍读盘且失败目标逐字节不变；超出预算时默认拒绝并提示按块分批填充（或允许调用方显式传流式/两遍读标志）。
   - **离散帧清单 `frame_indices[]` 延后至 v0.2 增量追加**（v0.1 聚焦连续区间 `push`）。
4. **帧级元数据大块解耦与 `CellCoord` 排序索引（修订 `ADR-0017`/`0019`）**：
   - 帧级定长元数据（`pos_valid`/`pos`/`sync_level`/`cell_valid`/`cell_coord`/必填与可空 `aux`）与波形 `F_chunk` 彻底解耦，合并为紧凑大块帧元表（独立 `F_meta_chunk`，默认 `4096–16384` 帧/块），取消每个 1B 标志单独建数据集与违反自然对齐的 `CUSTOM_STRUCT`。
   - 启用 `CellCoord` 时，在 `complete_scan()` 收尾阶段写出不可变的紧凑排序索引表 `(cell_coord -> frame_idx)`，支撑百 GB 无快照文件 `O(log N)` 毫秒级查回 `0~N` 帧。
5. **收口混合保留并修复状态机漏洞（修订 `ADR-0016`/`0018`）**：
   - Core 首版（M3）聚焦 **全波（`full_wave`）+ 伴生/旁路 C 扫快照**；将逐帧流式硬件特征（`wave_and_feature`）与选择性留波多态槽位随 `FeatureOnly` 一并归入 M4 统一设计，消除“契约承诺但磁盘无处落盘”的断层。
   - 新增 **`cancel_empty_scan()`**：允许 `ScanActive (N == 0)` 在尚未提交帧时安全废弃空 Scan 并回退 `FileOpen`，保住同文件内已完成的先序 Scan 可正常封存。
   - 修正 `complete_scan()` 与 `seal_with_failure()` 顺序：`seal_with_failure()` 禁止向报错句柄强行补写未 Flush 尾部，禁止降级已完成的 Scan，并明确守卫禁止 0-Scan 空壳封存。
6. **打通多区域拼接整体、复检溯源与多 Scan/按层快照（修订 `ADR-0017`）**：
   - 新增可选容器级轻量 **逻辑拼接组（`ScanGroup`）**，显式声明多 Scan 构成一个逻辑整体（含公共 `crs_ref` 与成员角色），保持底层原始波形按单 Scan 独立访问。
   - 伴生与旁路快照支持绑定 **1..N 个源 Scan**、支持在 `FileOpen` 下按 Scan **多次追加不可变伴生快照**、支持**按层独立 `status`/来源**（兑现 `ADR-0014`），并移除 `<=4 MiB` 强制无压缩连续存储规则冲突。
   - `reinspection_targets[]` 升级为多目标数组并预留可选轻量跨文件 `target_file_uuid`，容器层预留可选 `continuation_of_file_uuid`（纯元数据指针，不引入跨文件联合查询引擎）；`aux_columns.semantic_role` 增补 `"region_index"` / `"pass_index"` / `"scan_direction"`。
   - Windows 旁路快照更新优先采用**不可变版本化文件名 + 原子指针切换**，彻底避开 UMS 边看边重算时的 `MoveFileExW` 共享锁冲突。
7. **超声物理 Schema 分层跨 ABI 边界与必填核纠偏（修订 `ADR-0017`/`0020`）**：
   - 最小解码必填核走强类型 C11 结构体（`abidiff` 保护），并立即消除互操作歧义：明确 `SignalDescriptor` `msb` 移位掩码顺序、`log_db` 标度、`f32` 饱和、原始 `adc_sample_rate_hz` vs 硬件峰值压缩/抽取及 `surface_interface` 界面波声时列；明确 `POSE_6D_EULER` 数学约定与 `pose_matrix_4x4` 行列主序；新增可选 `crs_transforms` 刚体变换链；`ENCODER_I64` 支持逐轴有效掩码；`PhasedArray` `focal_law` 分离 `tx_probe_id`/`rx_probe_id` 支持 DMA/DLA 双阵并补全 `matrix_2d`/`annular` 几何；消除 HDF5 属性/DCPL/JSON 双份真理源。
   - 可选物理表（全仓勘误 ASTM DICONDE 超声标准为 **`E2663`**，补齐水浸/喷水模型、按探头/组/法则索引的 `wedge`/`pulser_receiver`/2D-TCG、TOFD PCS 与增益三分解）与 `VendorExtension` 走带机读 JSON Schema 的 UTF-8 JSON（v0.x 宽容演进，待 `D-09` 实机核对后随 `1.0` 冻结）；删去私有 `/blobs/` 与 `Region` 树环检测等 YAGNI 项。
8. **跨平台硬加固与薄垂直切片研发节奏（修订 `ADR-0009`/`0020`）**：
   - 固化跨平台互斥锁协议（进程内按 OS 文件 ID `(st_dev, st_ino)` / `FileIndex` 注册；跨进程在常驻句柄锁文件数据区外哨兵字节 `INT64_MAX - 1`，Linux `F_OFD_SETLK`、Windows `LockFileEx`）。
   - 固化 HDF5 静态单库初始化硬规：`H5dont_atexit()`、`H5PLset_loading_state(0)` + 静态 `H5Zregister(32015/32004)`、`H5Eset_auto2(..., NULL, NULL)`；Linux 发布版锁低 `glibc` 容器 + `-static-libstdc++ -static-libgcc -fvisibility=hidden -Wl,--exclude-libs,ALL`；Windows 统一 `/MT` 静态 CRT 与 UTF-8 路径防护。
   - 修正 `D-05` 压测目标为 **Extensible Array 二级分页（>=20,000 块）+ dense group + 大快照写入** 下的随机 `SIGKILL` 隔离恢复验证。
   - 解耦 `VAL-01` 运行时核验与离线测试报告格式；v0.x 延后 `SONAME`/`abidiff` 门禁至 `1.0-rc`。本次落盘后暂停文档扩写，立即起草极简 `uss.h` 并启动 **Linux + Windows MSVC（含 `.NET 4.8` 烟雾调用）薄垂直切片**（将 Windows 实测前移至 M2）。

## 后果

- Core v0.1 C11 接口数量与 `.NET` 双目标维护成本大幅下降（移除 `poll`、纯选择层、`CUSTOM_STRUCT`、SWMR 切换与 1.14 双实现）；
- 多区域拼接整体与跨接缝/跨文件复检在数据模型上全面打通；
- 消除了审查暴露的全部 P0 状态机死锁、死空间膨胀、小列碎裂、全局锁阻塞与跨平台打包隐雷；
- 下一步直接进入 M2 极简 `uss.h` 与代码驱动的薄垂直切片实现。
