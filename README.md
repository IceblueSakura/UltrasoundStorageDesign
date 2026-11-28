# UltrasoundStorageDesign

超声数据专用的规范化存取 SDK 设计项目。状态：已依据 [ADR-0001～ADR-0021](docs/decisions/README.md) 完成 **Core 首版定型与架构减痛重构**（Spec `0.3-draft` + [WIRE_FORMAT.md](docs/WIRE_FORMAT.md) `1.0-draft r2`）；即将停止文档扩张，进入极简 `uss.h` 与代码驱动的 Linux/Windows 薄垂直切片实现，不修改或重跑既往实验。

本产品由 UMS 实际需求驱动完善，同时面向其他扫描系统与外部分析，作为包含权威 schema 与读写能力的单一产品独立维护并开源（[ADR-0015](docs/decisions/0015-cross-system-data-delivery.md)～[ADR-0021](docs/decisions/0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md)）：

- **SDK Core（首版 M2/M3 聚焦）**：C++20 核心实现 + **极简 `push`-only 纯 C11 ABI** 静态自包含单库（打包 HDF5 2.x + zstd + lz4 + xxhash），首版绑定 **`.NET`（`net10.0` + `net48`，x64；Windows MSVC + `.NET 4.8` 烟雾闭环前移至 M2）**，官方 Python 绑定延后至 M4。包含：
  - 中立交付容器（不变 `FileInstanceUUID`、轻量 M:N `Region`、多区域逻辑拼接组 `ScanGroup`、多 `Scan`/`EndStatus`、`cancel_empty_scan()`、可选跨文件复检与续扫轻引线）；
  - 分扫描类型独立清晰的 Schema（**首版聚焦单晶与相控阵全波**，`wave_and_feature`/`FeatureOnly`/`FMC` 归 M4），实行“C11 强类型最小解码必填核 + ASTM E2339/**E2663** & NeXus 可选物理表（水浸/多探头/2D-TCG/PCS，JSON Schema）+ `crs_transforms` + 参数化曲面几何 + `VendorExtension`”；
  - 减痛物理 I/O 引擎：HDF5 2.x 非 SWMR 写出 1.10–1.14 兼容格式（取消 1.14 独立双实现门禁）、波形 `(F_chunk, K_chunk, S)` 1–4 MiB 与大块解耦帧元 `frames/meta`（`F_meta_chunk`）+ `CellCoord` 排序索引 `O(log N)` 查回、`{i8..u32, f32}` 按位无损、`none/shuffle+zstd/shuffle+lz4`、单一 `stored_xxh3` + `O(1)` 打开、**外部临时 `.wal` 增量追加 + 低频 `fsync` + `LIF-02` 独立恢复子进程隔离**，以及**只读 I/O 锁外并发 `pread`/`ReadFile`** + OS 文件 ID/哨兵字节跨进程锁；
  - Write-Once 生命周期与统一快照模型：`FileOpen` 态按 Scan 多次追加 1..N Scan/按层状态与来源伴生快照，封存后彻底不可变；离线派生写入**版本化 Write-Once 旁路容器 + 原子指针切换**，规避 Windows 边看边重算锁冲突；
  - 极简读取接口：统一连续区间 `push` 原语（砍去 `poll` 与 C ABI 纯选择层，离散帧清单留 v0.2）+ `staging_budget` 有界原子边界 + 块几何与容量查询对齐 UMS `Batch-of-SoA`。
- **独立可选扩展层（M4，只消费 Core 只读 API）**：① 窗口选峰扩展（[MEAS-01](docs/DATA_SPEC.md#meas-01)）；② 旁路 3D 空间索引与可插拔多回波代表选择扩展（[ACCESS-01](docs/DATA_SPEC.md#access-01)）。
- **明确排除**：UI/Workflow/设备控制、执行期进程内分发与上位机内存池、扫描复现、激光点云、标注/缺陷分析成果、复杂分析与额外导出/成果打包。

## 设计审阅与 M2 薄切片快速路线（5 份核心文档）

1. **[DESIGN.md](docs/DESIGN.md)**：两层架构全景、核心决策总览、需求基线（`R-01`–`R-20`）与排除范围。
2. **[DATA_SPEC.md](docs/DATA_SPEC.md)**：唯一权威数据与存储契约、逻辑模型、写入保护与恢复语义、不变量（`U-01`–`U-16`）与 `D-01`–`D-19` 状态总表。
3. **[SDK_CONTRACT.md](docs/SDK_CONTRACT.md)**：Core 首版工程合同——交付矩阵、编码 Profile、极简 `push`-only C11 ABI 与状态机、锁与跨平台加固、`.NET` 绑定与版本门禁。
4. **[WIRE_FORMAT.md](docs/WIRE_FORMAT.md)**：M2 HDF5 Wire Format 1.0 规范草案（`1.0-draft r2`），含外部 `.wal`、大块帧元、`cell_index` 与 H/P 样例。
5. **[DECISION_DIRECTIONS.md](docs/DECISION_DIRECTIONS.md)**：仅剩的待补实机事实输入、M2 薄切片执行任务与 v0.2/M4 后置项。

支撑文档（[SPEC_TEST_PLAN.md](docs/SPEC_TEST_PLAN.md) 访问场景映射与验证计划、[SCENARIO_AUDIT.md](docs/SCENARIO_AUDIT.md) 场景事实与历史基准局限）按需查阅；完整索引见 [文档索引](docs/README.md)，21 份已采纳决定见 [ADR 目录](docs/decisions/README.md)。

## 仓库组织

- `docs/`：设计全景、数据契约、工程合同、Wire 草案、ADR、验证计划与场景审计。
- `experiments/m1/`：既有 test-only 机制原型、探针与核对脚本，见其 [README](experiments/m1/README.md) 与 [报告](experiments/m1/REPORT.md)；不是 SDK，编码不是产品格式，旧证据不外推到新增能力。
- `experiments/runs/`、`testdata/`：本地运行输出与测试数据，已忽略，不作为设计依据。
- `archive/`：历史参考；仅保留压缩/单通道实验脚本，不是 SDK（见 [归档说明](archive/README.md)）。`archive/hdf5/` 为本地上游检出，父仓库忽略。
- `flake.nix` / `flake.lock`：开发环境入口与锁。

## 开发环境

从仓库根目录运行 `nix develop`。默认环境使用 flake 声明的 HDF5 2.x、libzstd、liblz4 与 CMake/Ninja 工具链，不依赖归档检出；可选 `hdf5-local` 见 `flake.nix`。本阶段不重跑既往实验与 benchmark。
