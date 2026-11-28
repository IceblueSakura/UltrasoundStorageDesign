# 决定记录（ADR）

[返回文档索引](../README.md)。每份记录一页，只写一个决定的背景、内容、理由与证据、后果及仍未决定的部分。规则正文仍以 [DATA_SPEC.md](../DATA_SPEC.md) 为唯一契约来源；ADR 说明为什么这样改，不另立第二套规范。待定项只登记在 DATA_SPEC 的 D 项，问题与候选见 [DECISION_DIRECTIONS.md](../DECISION_DIRECTIONS.md)。

| 编号 | 决定 | 状态 | 主要影响 |
|---|---|---|---|
| [ADR-0001](0001-stream-groups.md) | 引入同构流组；帧级附加记录统一承载 | 已采纳；由 ADR-0011 限定为原始波形 Core，并由 ADR-0016 降为原始波形物理引擎可选参考抽象（对外改为分扫描类型独立 Schema） | 逻辑模型、WAV-01、PAR-01、PA-01、FMC-01/02、MAP-01 |
| [ADR-0002](0002-durability-and-failure.md) | Flush 承诺、写失败态、提交记录与校验和；只写一次的 chunk 作为参考机制 | 已采纳（断电与 fsync 部分被 ADR-0008 替代；机制待 M2 取证） | WRT-01/02/03、IO-01、LIF-01/02、VAL-01 |
| [ADR-0003](0003-explicit-validity-bitmap.md) | 写入时必须提交完整有效性位图；字节序按数值语义交付 | 已采纳；适用范围由 ADR-0011 限定为原始波形槽位 | STA-01、WAV-02、WRT-01 |
| [ADR-0004](0004-concurrency-and-borrow-scope.md) | 进程内串行化、多进程只读已封存文件、poll 借用的结束条件 | 部分被 ADR-0021 修订（砍去 C ABI `poll` 借用，并将只读 chunk I/O 移出全局 HDF5 锁） | CORE-01、BUF-01、R-14 |
| [ADR-0005](0005-file-format-range.md) | 写出文件限定为 HDF5 1.10–1.14 可读的格式 | 保留 `v1.10–v1.14` 写出限制；1.14 独立读取器双实现门禁由 ADR-0021 取消 | ID-01、MAP-01、D-07 |
| [ADR-0006](0006-core-io-and-selection-layer.md) | 原始 Core I/O 与纯选择层 | 部分被 ADR-0016 / ADR-0021 修订（纯内存选择层移出 C11 存储 ABI，Core I/O 收敛为 push-only） | CORE-01、READ-01/02/03、FMC-02、IO-01、ACCESS-01 |
| [ADR-0007](0007-documentation-structure.md) | 引入 ADR、Spec 升为 0.3-draft、DECISION_DIRECTIONS 只列未决问题 | 已采纳 | 全部文档 |
| [ADR-0008](0008-process-crash-scope.md) | 持久化只覆盖进程崩溃，不考虑断电与操作系统崩溃；Flush 不要求 fsync | 高频 Flush 保留；低频 `complete_scan`/`seal`/旁路提交强制 `fsync` 由 ADR-0021 补充 | WRT-03、IO-01、MAP-02、D-05 |
| [ADR-0009](0009-review-contract-clarifications.md) | 首版 Tx×Rx 矩阵限于单个流组；SDK 检测并拒绝同一文件上的 Writer 与 Reader；失败态时活动的 Scan 封存后保持未完成 | 已采纳 | FMC-01、CORE-01、LIF-01、D-14 |
| [ADR-0010](0010-public-api-stability.md) | 公开 API 的稳定原则：C ABI 唯一稳定边界、64 位长度与显式缓冲、可扩展参数与预留标志、稳定的错误结果 | 已采纳 | API-01、D-10、D-12 |
| [ADR-0011](0011-ultrasound-business-boundary.md) | 承接 UMS 阶段业务基线，收敛超声专用 SDK 范围 | 已采纳；部分被 ADR-0016 调整（封存后原地替换改为 Write-Once 不可变＋旁路派生文件，基础取值与多回波选择移入扩展层） | BUS-01～MEAS-01、POS-01、D-01/D-09/D-11/D-13/D-16～D-18 |
| [ADR-0012](0012-basic-access-confirmed-and-deferred.md) | 同类观测仅选有效代表，前沿输出位置/时间与幅值 | 最新有效方向被 ADR-0014 替代；基础取值与多回波选择移入独立可选扩展层（ADR-0016） | ACCESS-01、MEAS-01、D-17/D-18 |
| [ADR-0013](0013-region-relations-and-subset-scope.md) | 目标区域与复检局部来源关系，五类重点访问及四类子集范围 | 业务范围已采纳；ADR-0016 确立区域为文件内独立实体（D-11）并重申跨文件复检归 D-19 | REL-01、SCAN-02、ACCESS-01、D-03/D-11/D-17/D-19 |
| [ADR-0014](0014-configurable-selection-and-snapshot-source.md) | 顶层统一指定选择函数、底层完整来源访问；快照实际来源不被当前代表替代 | 已采纳；多回波代表选择移出 Core 归独立可选扩展层，原始文件 Write-Once 不可变，快照历史来源不变原则保留（ADR-0016） | ACCESS-01、SNAP-01、D-16/D-17 |
| [ADR-0015](0015-cross-system-data-delivery.md) | SDK 面向 UMS 与其他系统承担跨系统数据交付；执行期分发归调用方；单写、封存后读取；跨文件组织暂不规划 | 已采纳业务边界；跨文件组织待 D-19 | BUS-01、REL-01、SCAN-01、D-11/D-19、R-20 |
| [ADR-0016](0016-tiered-core-mode-schemas-and-immutable-seal.md) | 两层 SDK 架构（Core + 独立可选扩展层）、分扫描类型独立 Schema、Write-Once 封存只读、解除 `h5py` 裸读并闭合 Q1–Q7 | 已采纳模型与边界决定；具体范围、机制与工程合同由 ADR-0017～0020 进一步定型 | DOC-01、CORE-01、BUS-01、RET-01、REL-01、SNAP-01、ACCESS-01、MEAS-01、SCAN-01/02、ID-01、LIF-01、D-15（关闭） |
| [ADR-0017](0017-core-v1-scope-and-domain-model.md) | Core 首版范围（单晶 + 相控阵 + 快照）、轻量 M:N `Region`、统一快照与 Write-Once 旁路容器、最小解码核＋可选物理表与可配置 `(F_chunk, K_chunk, S)` 分块 | 已采纳；多 Scan/按层快照、拼接组与跨文件复检引线、E2663 勘误等由 ADR-0021 扩展修正 | DOC-01、REL-01、SCAN-02、SNAP-01、META-01、MAP-01、SDK_CONTRACT；D-03/04/09/11/16 |
| [ADR-0018](0018-storage-engine-swmr-and-strict-lifecycle.md) | 正式选定 `MAP-02` + 按 Scan SWMR；拒绝正常空 Scan/空文件；写失败态禁原位重试；双槽提交全毁不可恢复；坚持 `push` 两阶段读 | 部分被 ADR-0021 替代（砍去 SWMR 与内嵌 `journal/` 改为外部 `.wal`、新增 `cancel_empty_scan()`、强制独立恢复子进程与低频 `fsync`） | MAP-02、WRT-01、IO-01、LIF-01/02、SDK_CONTRACT；D-05/D-10 |
| [ADR-0019](0019-wire-encoding-and-core-io-contracts.md) | 固定列式位置/`CellCoord`/附加记录、LSB-first packed bitset、越界与空选择整体拒绝、`{i8..u32, f32}` + `XXH3-64`、`none/shuffle+zstd/shuffle+lz4`、连续+离散按块合并 Batch 与容量查询 | 部分被 ADR-0021 修订（帧元合并大块 + `CellCoord` 排序索引、仅留 `stored_xxh3`、砍 `poll`/纯选择层、离散清单延至 v0.2、明示 `staging_budget`） | WAV-01/02、STA-01、POS-01/02、READ-02/03、CMP-01、SDK_CONTRACT；D-01/02/04/07/08/10 |
| [ADR-0020](0020-implementation-stack-bindings-and-versioning.md) | C++20 核心 + 纯 C11 ABI、静态自包含单库分发、首版仅交付 C ABI + `.NET`（`net10.0`/`net48`）并将 Python 延后至 M4、三套版本解耦与 `1.0` `abidiff` 门禁 | 已采纳；ADR-0021 补充跨平台硬加固（`H5dont_atexit`/低 `glibc`/`/MT`）、将 Windows 烟雾闭环前移至 M2 并将 `abidiff` 延至 `1.0-rc` | API-01、SDK_CONTRACT；D-07/D-12、角度 16 |
| [ADR-0021](0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md) | **HDF5 减痛重构（去 SWMR + 外部 `.wal` + 锁外并发读）、极简 `push`-only ABI、帧元大块与 `CellCoord` 索引、多区域拼接/跨文件复检引线与超声 P0 修复** | **已采纳（现行核心基线）** | 全核心文档与 `WIRE_FORMAT.md` |

`ADR-0011～0021` 明确修订或定型的范围以最新规则为准；其余既有工程决定保留原适用范围，不因文档收敛自动成为新增能力的实现方案或验收证据。

新增决定按下一个编号追加；被替代的记录保留原文，状态改为“已被 ADR-xxxx 替代”。
