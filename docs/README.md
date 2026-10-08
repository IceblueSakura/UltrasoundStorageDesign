# 文档索引

[返回项目入口](../README.md)。

**当前重点是为实际扫描场景和算法需求补充审计证据，而不是继续排列 benchmark 名次。** 架构已有基线，Spec 为 `0.1-draft`；产品编码、生产参数及实现未冻结。

## 阅读顺序与文档职责

| 顺序 | 文档 | 回答的问题 |
|---|---|---|
| 1 | [SCENARIO_AUDIT.md](SCENARIO_AUDIT.md) | 实际怎样扫描、算法需要什么、现有设计哪里需要证据？ |
| 2 | [DESIGN.md](DESIGN.md) | 已确认需求是什么，为什么这样划分职责，首版不做什么？ |
| 3 | [DATA_SPEC.md](DATA_SPEC.md) | 数据如何解释，哪些不变量必须成立，参考 HDF5 映射是什么？ |
| 4 | [SPEC_TEST_PLAN.md](SPEC_TEST_PLAN.md) | 如何把需求和场景变成独立可核查的样例与检查？ |
| 参考 | [BENCHMARK_REPORT.md](BENCHMARK_REPORT.md) | 为什么历史测量不足以决定生产布局和性能？ |

审计提纲不定义第二套 schema；需求只在 DESIGN 维护，规范与 D-01～D-10 待定项只在 DATA_SPEC 维护。审计发现冲突时显式修订这些来源，不靠脚本行为补全。

## 设计细节快速入口

- [记录模型](DATA_SPEC.md#rec-01)：共同触发、完整记录与来源身份。
- [固定解释与样本](DATA_SPEC.md#wav-01)：通道、dtype、采样轴与严格无损保存。
- [状态](DATA_SPEC.md#sta-01)、[位置](DATA_SPEC.md#pos-01)、[参数快照](DATA_SPEC.md#par-01)：有效性、历史关联与解释依赖。
- [HDF5 参考组织](DATA_SPEC.md#map-01)：SPLIT 路径和逻辑职责，尚非冻结格式。
- [写入与前缀](DATA_SPEC.md#wrt-01)、[封存](DATA_SPEC.md#lif-01)、[恢复](DATA_SPEC.md#lif-02)：确认边界和明确失败。
- [读取](DATA_SPEC.md#read-01)、[超 RAM](DATA_SPEC.md#cap-01)、[压缩](DATA_SPEC.md#cmp-01)：访问语义、有界资源与必要解码依赖。
- [场景到设计细节的对照](SCENARIO_AUDIT.md#5-设计细节的阅读路线)：按初始化、提交、确认、封存、读取逐项审查。

## 本轮使用方式

以一个真实扫描过程和一个具体算法为起点，使用[审计记录模板](SCENARIO_AUDIT.md#6-审计记录与收敛方法)记录输入、选择、顺序、解释依赖与预期结果。A/B/C/D 名称、位置数据或共享触发本身不等于已经定义了空间拓扑与算法契约。

先保留明确的未知项，再用小型正反例验证；没有真实执行的测试仍为 NOT_RUN。位置/身份等必要编码未闭合前，不宣称完整格式符合性；GPU 解压、超 RAM 和故障恢复均不能从小型热缓存实验外推。

历史脚本与本地结果退出主阅读路线，详见[归档说明](../archive/README.md)。本轮不运行、修复或扩展 benchmark，也不改写本地结果。
