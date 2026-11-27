# 文档索引

[返回项目入口](../README.md)。状态：已依据 [ADR-0001～ADR-0020](decisions/README.md) 完成 Core 首版设计与工程定型（Spec `0.3-draft`）；文档已完成高内聚拆分与合并（拆出 `SDK_CONTRACT.md`，原访问规划与历史基准局限分别并入 `SPEC_TEST_PLAN.md` 与 `SCENARIO_AUDIT.md`）。

## 文档导航与唯一职责

按 [设计维护原则](DESIGN.md#integration-policy) 与 [ADR-0007](decisions/0007-documentation-structure.md) 分工：每份文档承担单一职责，不重复维护第二套规则。

### 核心设计文档（必读）

| 顺序 | 文档 | 唯一职责 |
|---|---|---|
| 1 | [DESIGN.md](DESIGN.md) | 两层架构全景、核心架构决定总览、需求基线（`R-01`–`R-20`）与首版排除范围 |
| 2 | [DATA_SPEC.md](DATA_SPEC.md) | 唯一权威**数据与存储契约**：逻辑模型、分模式 Schema、位图/位置/快照语义、`MAP-02`+SWMR 耐久与恢复、不变量（`U-01`–`U-16`）与 `D-01`–`D-19` 状态总表 |
| 3 | [SDK_CONTRACT.md](SDK_CONTRACT.md) | **Core 首版工程合同**：首版交付矩阵、编码 Profile、C11 ABI 与状态机、连续/离散 Batch 与容量查询、C++20 静态单库、`.NET`（`net10.0`/`net48`）绑定与 `1.0` 门禁 |
| 4 | [DECISION_DIRECTIONS.md](DECISION_DIRECTIONS.md) | 仅列进入 M2 前仍缺的真实设备/负载事实、M2 冻结前细化清单与 M4/后置项 |
| 决策记录 | [decisions/](decisions/README.md) | `ADR-0001`–`0020`（一页一事），完整记录各项已采纳决定的背景、理由、证据与后果 |

### 验证与事实审计文档（按需查阅）

| 文档 | 唯一职责 |
|---|---|
| [SPEC_TEST_PLAN.md](SPEC_TEST_PLAN.md) | 访问场景映射与 TFM 边界、`H/P/F/W` 独立数值期望、`UC-01`–`UC-27` 与 `T-01`–`T-24` 验证规划、M0–M4 里程碑与 Core M3 验收门禁 |
| [SCENARIO_AUDIT.md](SCENARIO_AUDIT.md) | UMS 扫描流程与架构输入留档、设备/算法审计清单与历史微基准证据局限 |

## 契约章节快速入口

- **数据与存储契约（`DATA_SPEC.md`）**：
  - 产品与两层边界：[DOC-01](DATA_SPEC.md#doc-01)、[CORE-01](DATA_SPEC.md#core-01)、[API-01](DATA_SPEC.md#api-01)、[BUS-01](DATA_SPEC.md#bus-01)、[RET-01](DATA_SPEC.md#ret-01)、[REL-01](DATA_SPEC.md#rel-01)、[SNAP-01](DATA_SPEC.md#snap-01)、[ACCESS-01](DATA_SPEC.md#access-01)、[MEAS-01](DATA_SPEC.md#meas-01)
  - 容器、身份与模式数据：[逻辑模型](DATA_SPEC.md#logical-model)、[SCAN-01/02](DATA_SPEC.md#scan-01)、[REC-01/02](DATA_SPEC.md#rec-01)、[ID-01/02](DATA_SPEC.md#id-01)、[META-01](DATA_SPEC.md#meta-01)、[WAV-01/02](DATA_SPEC.md#wav-01)、[STA-01](DATA_SPEC.md#sta-01)、[POS-01/02](DATA_SPEC.md#pos-01)、[PA-01](DATA_SPEC.md#pa-01)、[PAR-01](DATA_SPEC.md#par-01)、[FMC-01/02](DATA_SPEC.md#fmc-01)
  - 物理引擎、耐久、读取与追踪：[MAP-01/02](DATA_SPEC.md#map-01)、[WRT-01–03](DATA_SPEC.md#wrt-01)、[IO-01](DATA_SPEC.md#io-01)、[LIF-01/02](DATA_SPEC.md#lif-01)、[READ-01–03](DATA_SPEC.md#read-01)、[BUF-01](DATA_SPEC.md#buf-01)、[CAP-01](DATA_SPEC.md#cap-01)、[CMP-01/02](DATA_SPEC.md#cmp-01)、[VAL-01](DATA_SPEC.md#val-01)、[不变量 U-01–U-16](DATA_SPEC.md#invariants)、[待定项 D-01–D-19](DATA_SPEC.md#open-items)
- **工程合同与交付规格（`SDK_CONTRACT.md`）**：[交付矩阵](SDK_CONTRACT.md#scope-matrix) · [编码 Profile](SDK_CONTRACT.md#encoding-profile) · [C11 ABI 与状态机](SDK_CONTRACT.md#c-abi-lifecycle) · [Batch 与容量查询](SDK_CONTRACT.md#core-io-batch) · [C++20 与 `.NET` 绑定](SDK_CONTRACT.md#platform-bindings) · [版本与 `1.0` 门禁](SDK_CONTRACT.md#versioning)

历史参考与实验入口：[归档说明](../archive/README.md) · [M1 实验说明](../experiments/m1/README.md)。
