# 文档索引

[返回项目入口](../README.md)。

**当前交付是测试用例编写前的一致设计基线。** Spec 为 `0.2-draft`，有用的设计参考已归入以下项目文档；产品编码、生产参数及实现未冻结。本轮不编写或运行测试。

## 阅读顺序与文档职责

| 顺序 | 文档 | 回答的问题 |
|---|---|---|
| 1 | [DESIGN.md](DESIGN.md) | 已确认需求是什么，为什么这样划分职责，本轮不做什么？ |
| 2 | [DATA_SPEC.md](DATA_SPEC.md) | Frame/事件/流、PA/FMC 如何解释，哪些不变量必须成立？ |
| 3 | [ACCESS_USE_CASE_PLAN.md](ACCESS_USE_CASE_PLAN.md) | 怎样选择和分批消费数据，访问结果如何追溯？ |
| 4 | [SPEC_TEST_PLAN.md](SPEC_TEST_PLAN.md) | H/P/F 的独立期望及 UC 集怎样验证，旧 T 项如何适配？ |
| 5 | [SCENARIO_AUDIT.md](SCENARIO_AUDIT.md) | 具体设备、坐标、算法负载与运行边界还缺什么证据？ |
| 参考 | [BENCHMARK_REPORT.md](BENCHMARK_REPORT.md) | 为什么历史测量不足以决定生产布局和性能？ |

文档按 [设计维护原则](DESIGN.md#integration-policy)分工：需求与理由只在 DESIGN 维护，活动契约、必要机制解释与 D 项只在 DATA_SPEC 维护；访问/测试规划不能反向新增规范。每项规则有一个维护位置，其他文档只作项目内引用与追踪。

## 设计细节快速入口

- [逻辑模型](DATA_SPEC.md#logical-model)：Scan、EventDefinition、WaveformStream 与 Frame 身份。
- [固定解释与样本](DATA_SPEC.md#wav-01)：流内 dtype/长度/采样轴固定，跨流异构及无损保存。
- [状态](DATA_SPEC.md#sta-01)、[位置](DATA_SPEC.md#pos-01)、[固定定义](DATA_SPEC.md#par-01)：观测状态、历史关联与定义复用。
- [PA 位置](DATA_SPEC.md#pa-01)、[FMC 映射](DATA_SPEC.md#fmc-01)、[矩阵访问](DATA_SPEC.md#fmc-02)：模式语义不由 shape 推测。
- [HDF5 组织边界](DATA_SPEC.md#map-01)：逻辑职责与物理组织分开，路径尚未冻结。
- [写入与前缀](DATA_SPEC.md#wrt-01)、[封存](DATA_SPEC.md#lif-01)、[恢复](DATA_SPEC.md#lif-02)：确认边界和明确失败。
- [读取](DATA_SPEC.md#read-01)、[超 RAM](DATA_SPEC.md#cap-01)、[压缩](DATA_SPEC.md#cmp-01)：访问语义、有界资源与必要解码依赖。
- [统一不变量](DATA_SPEC.md#invariants)、[UC 回归集](SPEC_TEST_PLAN.md#uc-regression)：规则与独立预期追踪。
- [剩余场景问题](SCENARIO_AUDIT.md)：从真实输入补充证据，不重开已采纳的模型决策。

## 本轮使用方式

先核对 DESIGN 的范围、DATA_SPEC 的逻辑契约与访问规划，再使用 SPEC_TEST_PLAN 中的 H/P/F、UC 素材及 T 追踪编写后续用例。具体设备或算法的剩余问题使用[审计记录模板](SCENARIO_AUDIT.md#6-审计记录与收敛方法)记录；A/B/C/D 名称、帧位置或共同 Frame 本身不等于空间拓扑、物理同步或算法正确性。

所有活动验证项仍为 NOT_RUN，旧 T-08 为已替代而非 PASS；此次不编写可执行用例、不生成样例或执行测试。访问覆盖只追踪项目内已定义用例。状态编码、错误结果容器等未决项不能为了测试提前定案；必要编码未闭合前不宣称完整格式符合性，GPU 解压、超 RAM 和恢复也不能由小样例外推。

历史脚本与本地结果退出主阅读路线，详见[归档说明](../archive/README.md)。本轮不运行、修复或扩展 benchmark，也不改写本地结果。
