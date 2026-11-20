# 决定记录（ADR）

[返回文档索引](../README.md)。每份记录一页，只写一个决定的背景、内容、理由与证据、后果及仍未决定的部分。规则正文仍以 [DATA_SPEC.md](../DATA_SPEC.md) 为唯一契约来源；ADR 说明为什么这样改，不另立第二套规范。尚未决定的问题只在 [DECISION_DIRECTIONS.md](../DECISION_DIRECTIONS.md) 和 DATA_SPEC 的 D 项中维护。

| 编号 | 决定 | 状态 | 主要影响 |
|---|---|---|---|
| [ADR-0001](0001-stream-groups.md) | 引入同构流组；帧级附加记录统一承载 | 已采纳 | 逻辑模型、WAV-01、PAR-01、PA-01、FMC-01/02、MAP-01 |
| [ADR-0002](0002-durability-and-failure.md) | Flush 承诺、写失败态、提交记录与校验和；只写一次的 chunk 作为参考机制 | 已采纳（断电与 fsync 部分被 ADR-0008 替代；机制待 M2 取证） | WRT-01/02/03、IO-01、LIF-01/02、VAL-01 |
| [ADR-0003](0003-explicit-validity-bitmap.md) | 写入时必须提交完整有效性位图；字节序按数值语义交付 | 已采纳 | STA-01、WAV-02、WRT-01 |
| [ADR-0004](0004-concurrency-and-borrow-scope.md) | 进程内串行化、多进程只读已封存文件、poll 借用的结束条件 | 已采纳 | CORE-01、BUF-01、R-14 |
| [ADR-0005](0005-file-format-range.md) | 写出文件限定为 HDF5 1.10–1.14 可读的格式 | 已采纳 | ID-01、MAP-01、D-07 |
| [ADR-0006](0006-core-io-and-selection-layer.md) | 原始 Core I/O 与纯选择层 | 工程划分保留，产品访问边界由 ADR-0011 修订 | CORE-01、READ-01/02/03、FMC-02、IO-01、ACCESS-01 |
| [ADR-0007](0007-documentation-structure.md) | 引入 ADR、Spec 升为 0.3-draft、DECISION_DIRECTIONS 只列未决问题 | 已采纳 | 全部文档 |
| [ADR-0008](0008-process-crash-scope.md) | 持久化只覆盖进程崩溃，不考虑断电与操作系统崩溃；Flush 不要求 fsync | 已采纳（部分替代 ADR-0002） | WRT-03、IO-01、MAP-02、D-05 |
| [ADR-0009](0009-review-contract-clarifications.md) | 首版 Tx×Rx 矩阵限于单个流组；SDK 检测并拒绝同一文件上的 Writer 与 Reader；失败态时活动的 Scan 封存后保持未完成 | 已采纳 | FMC-01、CORE-01、LIF-01、D-14 |
| [ADR-0010](0010-public-api-stability.md) | 公开 API 的稳定原则：C ABI 唯一稳定边界、64 位长度与显式缓冲、可扩展参数与预留标志、稳定的错误结果 | 已采纳 | API-01、D-10、D-12 |
| [ADR-0011](0011-ultrasound-business-boundary.md) | 承接 UMS 阶段业务基线，收敛超声专用 SDK 范围 | 已采纳；业务确认，非实现定版 | BUS-01～MEAS-01、POS-01、D-01/D-09/D-11/D-13/D-16～D-18 |
| [ADR-0012](0012-basic-access-confirmed-and-deferred.md) | 同类观测仅选有效代表，前沿输出位置/时间与幅值 | 最新有效方向被 ADR-0014 替代，其余边界保留 | ACCESS-01、MEAS-01、D-17/D-18 |
| [ADR-0013](0013-region-relations-and-subset-scope.md) | 目标区域与复检局部来源关系，五类重点访问及四类子集范围 | 业务范围已采纳，区域信息与模型待定 | REL-01、SCAN-02、ACCESS-01、D-03/D-11/D-17 |
| [ADR-0014](0014-configurable-selection-and-snapshot-source.md) | 顶层统一指定选择函数、底层完整来源访问；快照实际来源不被当前代表替代 | 已采纳业务边界，函数与配置机制暂缓 | ACCESS-01、SNAP-01、D-16/D-17 |
| [ADR-0015](0015-cross-system-data-delivery.md) | SDK 面向 UMS 与其他系统承担跨系统数据交付；执行期分发归调用方；单写、封存后读取；跨文件组织暂不规划 | 已采纳业务边界；跨文件组织待 D-19 | BUS-01、REL-01、SCAN-01、D-11/D-19、R-20 |

ADR-0011 明确修订的旧范围以新规则为准；其余工程决定保留原适用范围，不因本轮同步自动成为新增能力的实现方案。旧记录与实验不是新的产品验收证据。

新增决定按下一个编号追加；被替代的记录保留原文，状态改为"已被 ADR-xxxx 替代"。
