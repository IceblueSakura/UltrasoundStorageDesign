# ADR-0018：正式写入保护机制（MAP-02 + 按 Scan SWMR）、严格空对象与故障边界

- 状态：部分被 [ADR-0021](0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md) 替代（2026-11-28）：砍去按 Scan SWMR 与内嵌 `journal/` 改用外部临时 `.wal`，增加 `cancel_empty_scan()` 修复 `N==0` 死锁，禁止 `seal_with_failure` 补写未 Flush 尾部，低频边界强制 `fsync`，`LIF-02` 强制独立恢复子进程隔离，明示 `push` `staging_budget`。
- 规则落点：[MAP-02](../DATA_SPEC.md#map-02)、[WRT-01](../DATA_SPEC.md#wrt-01)、[IO-01](../DATA_SPEC.md#io-01)、[LIF-01](../DATA_SPEC.md#lif-01)、[LIF-02](../DATA_SPEC.md#lif-02)、[SDK_CONTRACT.md](../SDK_CONTRACT.md)；收口 `D-05`、`D-10` 核心机制。
- 来源：用户在 `ADR-0002`、`ADR-0008`、`ADR-0009` 与 M1 实验证据基础上的 P0 机制定型（2026-11-27）。

## 背景

[ADR-0002](0002-durability-and-failure.md) 与 [ADR-0008](0008-process-crash-scope.md) 确立了进程崩溃 Flush 后条件、写失败态与 `MAP-02` 参考机制，但正式采用 `MAP-02` 是否同时启用 SWMR、空 Scan/空文件能否封存、写失败态是否允许原位重试、双槽提交记录全毁是否盲扫抢救，以及 `push` 两阶段读是否放宽，长期作为 P0 项阻塞物理布局与状态机冻结。

## 决定

1. **正式选定 `MAP-02` + 按 Scan 启用 SWMR 作为核心写入保护机制（收口 `D-05` 选型）。**
   - 保留 `MAP-02` 全部机制：物理块按 `(F_chunk, K_chunk, S)` 组装整块、在 HDF5 全局锁外并行编解码并通过 `H5Dwrite_chunk` 只写一次；Flush 时半满尾块写入 A/B 双槽尾部日志，先 `H5Fflush` 数据与日志再写双交替槽提交记录并再次 `H5Fflush`（不要求 `fsync`，延续 `ADR-0008`）。
   - 每个 `Scan` 在非 SWMR 下完成其 HDF5 组/数据集创建后立即进入 **SWMR 写模式** 追加帧数据，以获取 HDF5 SWMR 的元数据写入顺序保护与标准 SWMR 只读恢复路径；当完成当前 `Scan`、切换新建下一 `Scan` 或封存前写入伴生 C 扫快照时，由 SDK Writer 在持续持有自身写者锁的前提下**透明执行 HDF5 句柄关闭与非 SWMR 重开**（SWMR 属内部实现，不外泄为公共 API）。
   - 对于 Scan 创建/封存前短暂非 SWMR 窗口内的进程崩溃，`LIF-02` 采用**原地只读打开**（内存中清除 superblock 状态标志，优先以公开只读 VFD 实现，绝不复制百 GB 文件、绝不修改源文件哈希）。M2 阶段仍须补充多级块索引大文件（数千块/Scan）的随机 SIGKILL 回归验证。
2. **严格拒绝正常空对象（收口 `D-05`/`D-10` 空对象边界）。**
   - **正常完成 Scan（`complete_scan`）要求该 Scan 至少已提交 1 帧（`N >= 1`）**；**正常封存文件（`seal`）要求文件至少包含 1 个已完成 Scan（`n_scans >= 1`）**。刚初始化尚未采到任何有效帧即中止的场景由调用方直接放弃并删除临时文件，不产出空 Scan 或无 Scan 封存文件。
   - **与既有故障及空区域语义的精确配合**：① 正常封存文件中仍合法包含“已声明但未采集”的空 `Region` 实体（例如 Scan A 完成、后续计划区域未执行）；② 若文件已有已完成 Scan，后续活动 Scan 尚未提交帧即遇写 I/O 错误时，走 `seal_with_failure` 仍按 [ADR-0009](0009-review-contract-clarifications.md) 保留已提交 Scan 并将失败活动 Scan 标记为未完成。
3. **写失败态一律禁止原位重试。** 写入、Flush、完成 Scan 或封存发生任何 I/O 错误进入写失败态后，严禁清除失败态继续向同一 Writer 追加；仅允许放弃关闭，或在全部已提交数据通过深度校验后执行带失败标记封存（`seal_with_failure`）。
4. **双槽提交记录全部损坏时直接判该 Scan 不可恢复。** `LIF-02` 严格以有效提交记录作为唯一可见范围权威；当某 Scan 的双槽提交记录均校验失败时，报告该 Scan 不可恢复（`N_r = 0`），不盲扫物理块或凭 dataset extent 猜测长度，同时不影响同文件内其他完好 Scan 的独立恢复。
5. **坚持 `push` 两阶段读（维护 `IO-01` 失败不变承诺）。** `push` 读取先读入并校验本次请求涉及的全部物理块，再解码写入调用者目标缓冲；任何 I/O 错误或校验失败均在改写目标缓冲前返回，保证调用者样本、位图与帧记录缓冲逐字节不变。

## 理由

- M1 实验表明，SWMR 写模式几乎零额外写入开销（与非 SWMR 持平），且能在主写入阶段额外加固 HDF5 自身元数据写入顺序，同时把崩溃恢复主路径落回标准 SWMR 只读打开。
- 拒绝 0 帧 Scan 与 0-Scan 正常封存可简化消费者判空与状态机分支，防止磁盘堆积无数据的空壳成果文件，同时不损害已有 Scan 的故障抢救与空 `Region` 缺口表达。
- M1 实测两阶段 `push` 读在压缩数据上仅增加约 6% 耗时（主要来自校验计算，改用 `XXH3-64` 后进一步微乎其微），完全没有必要放宽 `IO-01` 的强原子承诺。

## 后果与未决项

- `MAP-02` 由〔参考〕升格为 Core 正式写入保护基线；`DATA_SPEC.md` 与 `SDK_CONTRACT.md` 固化上述状态机边界。
- 仍需在 M2 实现早期执行单 Scan 多级块索引（数千块）的 `MAP-02 + SWMR` SIGKILL 验证（闭合 `D-05` 最终证据），并补全完整 C ABI 状态转换表与错误码枚举（`D-10`）。
