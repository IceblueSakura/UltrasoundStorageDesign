# UltrasoundStorageDesign

超声采集原始数据存储设计项目。当前处于**测试用例编写前的设计整合阶段**，数据 Spec 为 `0.2-draft`；设计语义、必要机制说明及验收素材均在项目内维护，尚未编写可执行用例或实现生产 SDK、检查器、H/P/F 样例。

## 当前重点：项目内一致的设计基线

固定 HDF5 2.x；多通道单晶、常规 PA、FMC 共用 `Scan` / `EventDefinition` / `WaveformStream` 和统一 `Frame`。采用固定采集定义、跨流异构/流内固定、PA 唯一帧位置及 FMC 显式 Tx/Rx 矩阵语义；单晶与阵列数据不混存。

1. [需求与架构决策](docs/DESIGN.md)：已采纳方向、职责及边界。
2. [数据 Spec](docs/DATA_SPEC.md)：唯一数据契约来源，含不变量及待定项。
3. [访问用例规划](docs/ACCESS_USE_CASE_PLAN.md)：Frame/Stream、PA 束、FMC 矩阵选择与消费边界，直接追踪项目 UC 用例。
4. [验证计划](docs/SPEC_TEST_PLAN.md)：H/P/F 独立期望及 UC-01～UC-16，全部 NOT_RUN。
5. [剩余场景审计](docs/SCENARIO_AUDIT.md)：实际设备、坐标解释、算法负载及运行协议证据。

本次只整合设计，不编写或运行测试。H/P/F 和 UC 是项目内的验收素材，后续才编写可执行用例、选择必要 test-only 编码及推进最小存取工具；不提前冻结产品字段、错误容器或物理参数。文档职责与修改边界见 [设计维护原则](docs/DESIGN.md#integration-policy)，阅读无需额外设计稿或参考网站。

完整导航见 [文档索引](docs/README.md)。历史 benchmark 仅保留[证据局限](docs/BENCHMARK_REPORT.md)，不用于冻结产品参数或宣称生产性能。

## 仓库组织

- `docs/`：当前设计、Spec、访问/验证规划及剩余审计问题。
- `archive/`：历史参考；只保留一套压缩实验脚本，不是 SDK。
- `archive/hdf5/`：本地上游检出，保留独立 Git，父仓库忽略。
- `flake.nix` / `flake.lock`：开发环境入口与锁。
- `experiments/runs/`：未来新实验的生成结果位置，已忽略；本轮未生成样例或实验。

[归档说明](archive/README.md)列出精简范围与 Git 历史入口。本地基准结果、缓存和 HDF5 检出不随父仓库分发；不删除本地结果，也不把它们视为有效验收证据。未来实现时再创建活动源码/测试目录，不向历史归档追加新 SDK。

## 开发环境

从仓库根目录运行 `nix develop`。默认环境使用 flake 声明的 HDF5 构建，不依赖归档检出；本轮未构建或验证运行环境。

可选 `hdf5-local` 依赖本地 `archive/hdf5/`，Git 源 flake 不包含该忽略目录。需要时使用包含工作树的路径 flake，例如 `nix build path:.#hdf5-local`，并确保源码存在。历史实验的风险说明只在[归档入口](archive/benchmarks/ultrasound_storage_baseline/README.md)维护，不作为推荐工作流。
