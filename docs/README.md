# 文档索引

[返回项目入口](../README.md)。

**当前逻辑设计基线已收束，首版工程合同仍待闭合。** Spec 保持 `0.2-draft`；产品编码、API/ABI 和物理参数未冻结。本轮只整理设计、待决策问题及阶段门禁，不实现 SDK 或运行产品测试。收束范围见 [DESIGN](DESIGN.md#baseline-closure)，不代表任何运行验证通过。

最终目标为通用超声数据存储管理 SDK，首版只做文件内管理 Core，未来按 Core + Extensions 扩展。同步读取支持 poll 的 SDK 内存借用和 push 的调用者目标复制，与分析/Batch 用途分别定义；Frame 优先、A-Scan 次之，不做帧内分块、update 或写入取消。波形采用单一有效性位图、无效槽位零填充，有效样本原样保存，不另分 payload 存在性与业务有效性。普通写不立即落盘，显式 Flush 强制落盘；批次失败机制、数据/位图布局及接口仍待讨论。本阶段不调优或设计部署，决定见 [Core 范围](DESIGN.md#core-scope)。

## 阅读顺序与文档职责

| 顺序 | 文档 | 回答的问题 |
|---|---|---|
| 1 | [DESIGN.md](DESIGN.md) | 已确认需求是什么，为什么这样划分职责，本轮不做什么？ |
| 2 | [DATA_SPEC.md](DATA_SPEC.md) | Frame/事件/流、PA/FMC 如何解释，哪些不变量必须成立？ |
| 3 | [ACCESS_USE_CASE_PLAN.md](ACCESS_USE_CASE_PLAN.md) | 分析/Batch 与 poll/push 如何组合，关联、借用期及数据/有效性位图接口还缺什么？ |
| 4 | [SPEC_TEST_PLAN.md](SPEC_TEST_PLAN.md) | H/P/F/W 的独立期望及 UC 集怎样验证，旧 T 项如何适配？ |
| 5 | [SCENARIO_AUDIT.md](SCENARIO_AUDIT.md) | 具体设备、坐标、算法负载与运行边界还缺什么证据？ |
| 决策入口 | [DECISION_DIRECTIONS.md](DECISION_DIRECTIONS.md) | 哪些问题优先决定，候选方案及影响是什么，需要哪些输入？建议未自动采纳，不是第二套规范或待定项账本 |
| 参考 | [BENCHMARK_REPORT.md](BENCHMARK_REPORT.md) | 为什么历史测量不足以决定生产布局和性能？ |

文档按 [设计维护原则](DESIGN.md#integration-policy)分工：需求与理由只在 DESIGN 维护，活动契约、必要机制解释与 D 项只在 DATA_SPEC 维护；访问/测试规划不能反向新增规范。每项规则有一个维护位置，其他文档只作项目内引用与追踪。

## 设计细节快速入口

- [Core 边界](DATA_SPEC.md#core-01)、[元信息组织](DATA_SPEC.md#meta-01)：文件内管理、公共描述与类型/版本内容；完整领域 schema 后置。
- [逻辑模型](DATA_SPEC.md#logical-model)：Scan、EventDefinition、WaveformStream 与 Frame 身份。
- [工件容器与多 Scan](DATA_SPEC.md#scan-01)、[Scan 映射关系待定边界](DATA_SPEC.md#scan-02)：独立 Scan 承载分块/复扫/精扫；区域、来源及坐标关系待决策，不自动融合或替代。
- [固定解释与样本](DATA_SPEC.md#wav-01)：流内 dtype/长度/采样轴固定，跨流异构及无损保存。
- [有效性位图](DATA_SPEC.md#sta-01)、[位置](DATA_SPEC.md#pos-01)、[固定定义](DATA_SPEC.md#par-01)：有效样本保真、无效零填充、历史关联与定义复用。
- [PA 位置](DATA_SPEC.md#pa-01)、[FMC 映射](DATA_SPEC.md#fmc-01)、[矩阵访问](DATA_SPEC.md#fmc-02)：模式语义不由 shape 推测。
- [HDF5 组织边界](DATA_SPEC.md#map-01)：逻辑职责与物理组织分开，路径尚未冻结。
- [写入与前缀](DATA_SPEC.md#wrt-01)、[Flush](DATA_SPEC.md#wrt-03)、[调用级强原子性](DATA_SPEC.md#io-01)、[封存](DATA_SPEC.md#lif-01)、[恢复](DATA_SPEC.md#lif-02)：成功/失败边界及持久化目标，机制待设计验证。
- [读取](DATA_SPEC.md#read-01)、[内容交付](DATA_SPEC.md#read-03)、[poll/push 缓冲](DATA_SPEC.md#buf-01)、[超 RAM](DATA_SPEC.md#cap-01)、[压缩](DATA_SPEC.md#cmp-01)：借用/复制、只读等价、Frame/Batch 优先与有界资源。
- [统一不变量](DATA_SPEC.md#invariants)、[UC 回归集](SPEC_TEST_PLAN.md#uc-regression)：规则与独立预期追踪。
- [剩余场景问题](SCENARIO_AUDIT.md)：从真实输入补充证据，不重开已采纳的模型决策。

## 本轮使用方式

后续从[决策顺序](DECISION_DIRECTIONS.md#decision-order)选择一组问题，结合[角度导航](DECISION_DIRECTIONS.md#角度导航)补充事实并讨论选项。D 项及其阶段闭合依据仍只在 [DATA_SPEC](DATA_SPEC.md#closure-gates) 维护；优先级不等于已作出决定，也不自动启动实现或测试。

正式格式/API 冻结前先取得写入旧数据保护、Flush 和绑定生命周期的小规模可行性证据；完整规模/故障覆盖及声明平台的 SDK 验收在 M3 汇总。推进顺序和唯一验收出口见 [里程碑](SPEC_TEST_PLAN.md#milestones)及 [Core 初版验收门禁](SPEC_TEST_PLAN.md#core-acceptance)。不得把临时工具可运行当成 SDK 已验收。

先核对 DESIGN 的范围、DATA_SPEC 的逻辑契约与访问规划，再使用 SPEC_TEST_PLAN 中的 H/P/F/W、UC 素材及 T 追踪编写后续用例。具体设备或算法的剩余问题使用[审计记录模板](SCENARIO_AUDIT.md#6-审计记录与收敛方法)记录；A/B/C/D 显示名称、帧位置或共同 Frame 本身不等于空间拓扑、物理同步或算法正确性。

所有活动验证项仍未执行：UC-18 映射关系待决策为 BLOCKED，其余 UC 及活动 T 项为 NOT_RUN，旧 T-08 为已替代而非 PASS；此次不编写可执行用例、不生成样例或执行测试。访问覆盖只追踪项目内已定义用例。映射关系模型、状态编码、错误结果容器等未决项不能为了测试提前定案；必要模型/编码未闭合前不宣称完整格式符合性，GPU 解压、超 RAM 和恢复也不能由小样例外推。

历史脚本与本地结果退出主阅读路线，详见[归档说明](../archive/README.md)。本轮不运行、修复或扩展 benchmark，也不改写本地结果。
