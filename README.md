# UltrasoundStorageDesign

超声采集原始数据存储设计项目。当前为逻辑架构与数据 Spec `0.1-draft`，尚未实现生产 SDK、符合性检查器或完整样例。

## 当前重点：扫描场景与算法需求审计

从实际采集动作和算法输入出发，检查记录模型、位置关联、数值解释、参数历史和访问方式是否充分，再决定物理布局与性能参数。现有约束作为审计基线，未确认事项不靠历史实验默认值补齐。

1. [扫描场景与算法审计](docs/SCENARIO_AUDIT.md)：讨论主题、设计细节索引和证据记录模板。
2. [需求与架构决策](docs/DESIGN.md)：已确认的需求、职责及首版边界。
3. [数据 Spec](docs/DATA_SPEC.md)：唯一数据契约来源，含参考 HDF5 映射与待定项。
4. [验证计划](docs/SPEC_TEST_PLAN.md)：将场景证据转成可核查的正反例；测试尚未执行。

完整导航见 [文档索引](docs/README.md)。历史 benchmark 仅保留[证据局限](docs/BENCHMARK_REPORT.md)，不用于冻结产品参数或宣称生产性能。

## 仓库组织

- `docs/`：当前审计材料、设计、Spec 和验证计划。
- `archive/`：历史参考；只保留一套压缩实验脚本，不是 SDK。
- `archive/hdf5/`：本地上游检出，保留独立 Git，父仓库忽略。
- `flake.nix` / `flake.lock`：开发环境入口与锁。
- `experiments/runs/`：未来新实验的生成结果位置，已忽略；本轮未生成新实验。

[归档说明](archive/README.md)列出精简范围与 Git 历史入口。本地基准结果、缓存和 HDF5 检出不随父仓库分发；不删除本地结果，也不把它们视为有效验收证据。未来实现时再创建活动源码/测试目录，不向历史归档追加新 SDK。

## 开发环境

从仓库根目录运行 `nix develop`。默认环境使用 flake 声明的 HDF5 构建，不依赖归档检出；本轮未构建或验证运行环境。

可选 `hdf5-local` 依赖本地 `archive/hdf5/`，Git 源 flake 不包含该忽略目录。需要时使用包含工作树的路径 flake，例如 `nix build path:.#hdf5-local`，并确保源码存在。历史实验的风险说明只在[归档入口](archive/benchmarks/ultrasound_storage_baseline/README.md)维护，不作为推荐工作流。
