# UltrasoundStorageDesign

超声数据专用的规范化存取 SDK 设计项目。状态：已承接 UMS 确认的阶段性业务基线，仍处于 Craft 阶段；Spec `0.3-draft`，完整模型、格式/API 与首发范围未冻结，尚无产品 SDK。

从 UMS 实际需求完善，后续作为包含 schema 和访问能力的单一产品独立维护并开源。当前范围：

- **超声数据**：原始波形、解释已有数据必需的模式参数与硬件/几何信息、必要数据关系、C 扫特征值快照；支持全波、仅特征和混合保留。见 [业务范围](docs/DATA_SPEC.md#bus-01)与[保留内容](docs/DATA_SPEC.md#ret-01)。
- **基础能力**：规范数据子集提取与读取、底层来源与顶层代表访问、文件输入的明确窗口内基础幅值和位置/时间取值。布局规划用于确定存取优化重点，不限制其它布局，也不做复杂处理或额外转换。见 [访问](docs/DATA_SPEC.md#access-01)与[基础取值](docs/DATA_SPEC.md#meas-01)。
- **快照与保护**：允许重开后新增/替换指定快照；原始采集事实不变，失败保留旧成果。见 [SNAP-01](docs/DATA_SPEC.md#snap-01)。
- **明确排除**：UI/Workflow/设备控制、扫描复现、激光点云、标注与缺陷分析成果、复杂分析和额外导出/成果打包。
- **仍待细化**：必要关系、参数范围、优先布局、代表波形规则、基础取值含义和快照组织；混合扫描范围暂不确定。见 [待定项](docs/DATA_SPEC.md#open-items)。

既有 HDF5、流组/Frame、poll/push 等工程设计在适用的原始波形 Core 路径中保留，不等于所有新能力的实现已确定。本次仅同步文档，不修改或运行既往实验代码、测试及 benchmark；旧证据不外推到新增能力。当前不规划许可证或定版 API。

已采纳决定的背景与证据见 [ADR](docs/decisions/README.md)，尚未决定的问题见 [待决策问题](docs/DECISION_DIRECTIONS.md)，完整导航见 [文档索引](docs/README.md)。

## 仓库组织

- `docs/`：设计、Spec、ADR、访问/验证规划及场景审计。
- `experiments/m1/`：临时的 test-only 原型、机制探针与核对脚本，见其 [README](experiments/m1/README.md) 与 [报告](experiments/m1/REPORT.md)；不是 SDK，编码不是产品格式。
- `experiments/runs/`：实验生成结果，已忽略。
- `testdata/`：本地临时测试数据，已忽略，不作为设计依据。
- `archive/`：历史参考；只保留一套压缩实验脚本，不是 SDK。`archive/hdf5/` 是本地上游检出，父仓库忽略。
- `flake.nix` / `flake.lock`：开发环境入口与锁。

[归档说明](archive/README.md)列出精简范围与 Git 历史入口。本地基准结果、缓存和 HDF5 检出不随父仓库分发，也不视为有效验收证据。

## 开发环境

从仓库根目录运行 `nix develop`。默认环境使用 flake 声明的 HDF5 2.x 构建（含 zlib/deflate），不依赖归档检出。

可选 `hdf5-local` 依赖本地 `archive/hdf5/`，Git 源 flake 不包含该忽略目录。需要时使用包含工作树的路径 flake，例如 `nix build path:.#hdf5-local`，并确保源码存在。历史实验的风险说明只在[归档入口](archive/benchmarks/ultrasound_storage_baseline/README.md)维护。
