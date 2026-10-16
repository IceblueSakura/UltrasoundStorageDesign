# UltrasoundStorageDesign

通用超声数据存储管理 SDK 设计项目。首版只做基于 HDF5 的文件内管理 **Core**，未来其他能力按 Core + Extensions 扩展。当前处于**测试用例编写前的设计整合阶段**，Spec 为 `0.2-draft`；尚未编写可执行用例或实现 SDK、检查器、H/P/F/W 样例。

## 当前重点：项目内一致的设计基线

固定 HDF5 2.x；多通道单晶、常规 PA、FMC 共用 `Scan` / `EventDefinition` / `WaveformStream` 和统一 `Frame`。采用固定采集定义、跨流异构/流内固定、PA 唯一帧位置及 FMC 显式 Tx/Rx 矩阵语义；单晶与阵列数据不混存。

一个文件代表一个工件的扫描集合，允许多个独立 Scan 承载分块扫描、复扫/精扫；每个 Scan 的区域、来源和坐标映射关系保持待决策，不自动拼接或覆盖旧结果。Scan 内定义固定、Frame 轴独立；单写者顺序完成 Scan，整个文件封存后只读。详见 [多 Scan 契约](docs/DATA_SPEC.md#scan-01)。

元信息及位置采用必要公共描述＋带类型/版本内容，不在本阶段完善领域 schema。位置描述 Scan 内固定、每帧一份值，PA 所有声束共用它；其他坐标以额外 dataset 按帧关联。同步读取支持 poll（SDK 内存只读借用，下次读取/关闭时失效）及 push（复制到调用者指定缓冲）。这与分析/Batch 内容交付分别定义；Frame/Batch 优先、A-Scan 次之，单 Frame 不分块，不做位置查询或 update。

波形按[单一有效性位图](docs/DATA_SPEC.md#sta-01)管理：每槽位一位、默认无效；调用者标记有效且通过结构校验的样本原样保存，包括真实全 0。无效槽位零填充，不要求提供或保留其输入样本，不再区分缺失与“有值但业务无效”；读取同时交付位图，不把填充值当真实回波。SDK 不做业务合法性判断，结构/解码/I/O 错误仍报错；位图打包及具体 API 待定。

单读单写、无并发 Reader 或线程安全保证；目标最新 Linux LTS/Windows 10+，优先 Python/.NET Framework 4.8，倾向 C/C++/pybind11，具体绑定待定。写入同步消费调用者输入，无取消，普通写入不立即落盘，显式 Flush 强制落盘。I/O 失败时 push 目标不变、poll 不返回部分新视图且旧借用不延寿；写失败无新增提交且旧数据不变，均报告原因/错误码，不要求崩溃事务。机制待验证，见 [Core 范围](docs/DESIGN.md#core-scope)。

1. [需求与架构决策](docs/DESIGN.md)：已采纳方向、职责及边界。
2. [数据 Spec](docs/DATA_SPEC.md)：唯一数据契约来源，含不变量及待定项。
3. [访问用例规划](docs/ACCESS_USE_CASE_PLAN.md)：分析结果与 Batch 只读视图、Frame/流/PA/FMC 及位置/元信息关联；数据/有效性位图布局及 API 仍待讨论。
4. [验证计划](docs/SPEC_TEST_PLAN.md)：H/P/F 及多 Scan 工件样例 W 的独立期望、UC-01～UC-19；均未执行，UC-18 映射关系待决策而 BLOCKED，其余 UC 为 NOT_RUN。
5. [剩余场景审计](docs/SCENARIO_AUDIT.md)：实际设备、坐标解释、算法负载及运行协议证据。

本次只整合设计，不编写或运行测试，不做细节调优或部署方案。负载以连续批量写、Frame 随机读及上传 GPU 前的 Batch 读为主，A-Scan 随机读为次级；返回主机指针不等于 GPU 上传、零拷贝或 GPU 解压。H/P/F/W 和 UC 是验收素材，后续才编写可执行用例及推进最小存取工具。文档职责与修改边界见 [设计维护原则](docs/DESIGN.md#integration-policy)。

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
