# UltrasoundStorageDesign

超声数据专用的规范化存取 SDK 设计项目。状态：已依据 [ADR-0001～ADR-0020](docs/decisions/README.md) 完成 **Core 首版架构与工程定型**（Spec `0.3-draft`）；准备进入 M2 wire 格式、C11 头文件细化与多级索引崩溃取证，不修改或重跑既往实验。

本产品由 UMS 实际需求驱动完善，同时面向其他扫描系统与外部分析，作为包含权威 schema 与读写能力的单一产品独立维护并开源（[ADR-0015](docs/decisions/0015-cross-system-data-delivery.md)～[ADR-0020](docs/decisions/0020-implementation-stack-bindings-and-versioning.md)）：

- **SDK Core（首版 M2/M3 聚焦）**：C++20 核心实现 + 纯 C11 ABI 静态自包含单库（打包 HDF5 2.x + zstd + lz4），首版绑定 **`.NET`（`net10.0` + `net48`，x64）**（官方 Python 绑定延后至 M4）。包含：
  - 中立交付容器（不变 `FileInstanceUUID`、轻量 M:N `Region`、多 `Scan` 与 `EndStatus`，工件与 Run 可选）；
  - 分扫描类型独立清晰的 Schema（**首版聚焦单晶与相控阵**，预留 `FeatureOnly` 与 `FMC`），实行“最小解码必填核 + DICONDE/NeXus 强类型可选物理表 + 参数化曲面几何 + `VendorExtension`”；
  - 共享物理 I/O 引擎：HDF5 2.x 写出 1.10–1.14 可读格式、可配置 `(F_chunk, K_chunk, S)` 分块（默认 1–4 MiB）、`{i8..u32, f32}` 按位无损、`none/shuffle+zstd/shuffle+lz4`、`XXH3-64` 逐块校验、**`MAP-02` + 按 Scan SWMR** 进程崩溃保护与 `LIF-02` 原地只读恢复；
  - Write-Once 生命周期与统一快照模型：原始文件封存前可选写 1 次伴生 C 扫快照后彻底不可变（正常完成/封存拒空对象）；离线派生快照写入独立的 **Write-Once 旁路派生容器**（临时文件 + 原子 `rename` 替换）；
  - 原生高效读写：连续 `(start, count)` + 离散帧清单（按块合并解码）双 Batch、`poll`/两阶段 `push`、块几何与容量查询对齐 UMS `Batch-of-SoA`，以及触发号/声束/通道/样本窗口 + 可选 `CellCoord[Frame]` 寻址。自描述不承诺外部 `h5py` 裸翻内部路径。
- **独立可选扩展层（M4，只消费 Core 只读 API）**：① 窗口选峰扩展（[MEAS-01](docs/DATA_SPEC.md#meas-01)）；② 旁路 3D 空间索引与可插拔多回波代表选择扩展（[ACCESS-01](docs/DATA_SPEC.md#access-01)）。
- **明确排除**：UI/Workflow/设备控制、执行期进程内分发与上位机内存池、扫描复现、激光点云、标注/缺陷分析成果、复杂分析与额外导出/成果打包。

## 设计审阅与 M2 准备快速路线（4 份核心文档）

1. **[DESIGN.md](docs/DESIGN.md)**：两层架构全景、核心决策总览、需求基线（`R-01`–`R-20`）与排除范围。
2. **[DATA_SPEC.md](docs/DATA_SPEC.md)**：唯一权威数据与存储契约、逻辑模型、`MAP-02`+SWMR 语义、不变量（`U-01`–`U-16`）与 `D-01`–`D-19` 状态总表。
3. **[SDK_CONTRACT.md](docs/SDK_CONTRACT.md)**：Core 首版工程合同——交付矩阵、编码 Profile、C11 ABI 与状态机、Batch/缓冲合同、C++20 静态打包、`.NET` 绑定与 `1.0` 版本门禁。
4. **[DECISION_DIRECTIONS.md](docs/DECISION_DIRECTIONS.md)**：仅剩的 M2 待补设备事实输入、冻结前细化任务与 M4 后置项。

支撑文档（[SPEC_TEST_PLAN.md](docs/SPEC_TEST_PLAN.md) 访问场景映射与验证计划、[SCENARIO_AUDIT.md](docs/SCENARIO_AUDIT.md) 场景事实与历史基准局限）按需查阅；完整索引见 [文档索引](docs/README.md)，20 份已采纳决定见 [ADR 目录](docs/decisions/README.md)。

## 仓库组织

- `docs/`：设计全景、数据契约、工程合同、ADR、验证计划与场景审计。
- `experiments/m1/`：既有 test-only 机制原型、探针与核对脚本，见其 [README](experiments/m1/README.md) 与 [报告](experiments/m1/REPORT.md)；不是 SDK，编码不是产品格式，旧证据不外推到新增能力。
- `experiments/runs/`、`testdata/`：本地运行输出与测试数据，已忽略，不作为设计依据。
- `archive/`：历史参考；仅保留压缩/单通道实验脚本，不是 SDK（见 [归档说明](archive/README.md)）。`archive/hdf5/` 为本地上游检出，父仓库忽略。
- `flake.nix` / `flake.lock`：开发环境入口与锁。

## 开发环境

从仓库根目录运行 `nix develop`。默认环境使用 flake 声明的 HDF5 2.x、libzstd、liblz4 与 CMake/Ninja 工具链，不依赖归档检出；可选 `hdf5-local` 见 `flake.nix`。本阶段不重跑既往实验与 benchmark。
