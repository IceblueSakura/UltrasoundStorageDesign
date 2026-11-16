# 文档索引

[返回项目入口](../README.md)。状态：已同步 UMS 阶段性业务基线，Spec `0.3-draft`；当前只细化需求，不定版 API，不修改或重跑既往代码/测试。

## 阅读顺序与文档职责

| 顺序 | 文档 | 回答的问题 |
|---|---|---|
| 1 | [DESIGN.md](DESIGN.md) | 已确认需求是什么，为什么这样划分职责，首版不做什么？ |
| 2 | [DATA_SPEC.md](DATA_SPEC.md) | 超声业务合同、保留状态、必要解释、快照及基础访问是什么，既有原始 Core 模型如何限定适用范围？ |
| 3 | [decisions/](decisions/README.md) | 每个已采纳决定的背景、理由、证据与后果 |
| 4 | [ACCESS_USE_CASE_PLAN.md](ACCESS_USE_CASE_PLAN.md) | 代表/来源访问、子集、快照和基础取值如何覆盖业务场景；哪些仍只是原始 Core 工程路径？ |
| 5 | [SPEC_TEST_PLAN.md](SPEC_TEST_PLAN.md) | H/P/F/W 的独立期望、UC 与 T 项怎样验证，里程碑与验收门禁是什么？ |
| 6 | [SCENARIO_AUDIT.md](SCENARIO_AUDIT.md) | 具体设备、坐标、算法负载与运行边界还缺什么证据？ |
| 决策入口 | [DECISION_DIRECTIONS.md](DECISION_DIRECTIONS.md) | 尚未决定的问题、候选方案、影响及所需输入 |
| 参考 | [BENCHMARK_REPORT.md](BENCHMARK_REPORT.md) | 为什么历史测量不足以决定生产布局和性能？ |

分工按 [设计维护原则](DESIGN.md#integration-policy) 与 [ADR-0007](decisions/0007-documentation-structure.md)：需求与理由在 DESIGN，规则与 D 项只在 DATA_SPEC，决定理由在 ADR；其他文档引用规则编号，不重述规则。

## 设计细节快速入口

- [产品边界](DATA_SPEC.md#bus-01)、[保留内容与状态](DATA_SPEC.md#ret-01)、[必要关系与模式解释](DATA_SPEC.md#rel-01)
- [快照与后续保存](DATA_SPEC.md#snap-01)、[布局/分层/子集访问](DATA_SPEC.md#access-01)、[基础取值](DATA_SPEC.md#meas-01)
- [本轮确认与修订依据](decisions/0011-ultrasound-business-boundary.md)、[业务细化入口](DECISION_DIRECTIONS.md#business-next)
- [Core 边界与并发](DATA_SPEC.md#core-01)、[元信息组织](DATA_SPEC.md#meta-01)
- [逻辑模型](DATA_SPEC.md#logical-model)：Scan、EventDefinition、WaveformStream、StreamGroup 与 Frame 身份
- [工件容器与多 Scan](DATA_SPEC.md#scan-01)、[Scan 映射关系待定边界](DATA_SPEC.md#scan-02)
- [流组固定解释与样本](DATA_SPEC.md#wav-01)、[有效性位图](DATA_SPEC.md#sta-01)、[位置与帧级附加记录](DATA_SPEC.md#pos-01)、[固定定义](DATA_SPEC.md#par-01)
- [PA 位置](DATA_SPEC.md#pa-01)、[FMC 映射](DATA_SPEC.md#fmc-01)、[矩阵访问](DATA_SPEC.md#fmc-02)
- [HDF5 组织边界](DATA_SPEC.md#map-01)、[写入保护参考机制](DATA_SPEC.md#map-02)
- [提交与写失败态](DATA_SPEC.md#wrt-01)、[提交记录](DATA_SPEC.md#wrt-02)、[Flush](DATA_SPEC.md#wrt-03)、[调用级原子性](DATA_SPEC.md#io-01)、[封存](DATA_SPEC.md#lif-01)、[恢复](DATA_SPEC.md#lif-02)
- [读取](DATA_SPEC.md#read-01)、[选择层](DATA_SPEC.md#read-02)、[内容交付](DATA_SPEC.md#read-03)、[poll/push 缓冲](DATA_SPEC.md#buf-01)、[超 RAM](DATA_SPEC.md#cap-01)、[压缩](DATA_SPEC.md#cmp-01)
- [统一不变量](DATA_SPEC.md#invariants)、[待定项](DATA_SPEC.md#open-items)、[UC 回归集](SPEC_TEST_PLAN.md#uc-regression)

## 使用方式

先从 [业务细化入口](DECISION_DIRECTIONS.md#business-next) 继续明确未决含义；确认后的规则只写回 DATA_SPEC，理由进入 ADR。当前业务确认不要求重跑旧实验或闭合全部工程项；既有 [里程碑](SPEC_TEST_PLAN.md#milestones) 与 [Core 门禁](SPEC_TEST_PLAN.md#core-acceptance) 保留供后续对应范围使用，不代替新增业务验收。临时工具可运行不等于 SDK 已验收，test-only 编码不是产品格式。

历史脚本与本地结果见[归档说明](../archive/README.md)。
