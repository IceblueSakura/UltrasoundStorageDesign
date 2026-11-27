# ADR-0006：Core I/O 按 Scan、帧和流组交付，帧内选择是纯选择层

- 状态：原始波形 Core 工程划分保留（2026-10-24，Spec 0.3-draft）；由 [ADR-0011](0011-ultrasound-business-boundary.md) 与 [ADR-0016](0016-tiered-core-mode-schemas-and-immutable-seal.md) 明确其归属 SDK Core 原始波形路径，选峰与 3D 空间索引/多回波选择归独立可选扩展层。
- 规则落点：[CORE-01](../DATA_SPEC.md#core-01)、[READ-01](../DATA_SPEC.md#read-01)、[READ-02](../DATA_SPEC.md#read-02)、[READ-03](../DATA_SPEC.md#read-03)、[FMC-02](../DATA_SPEC.md#fmc-02)、[IO-01](../DATA_SPEC.md#io-01)
- 仍未决定：Batch 帧选择语法、结果容器与错误合同（D-10）

## 背景

单 Frame 不分块，读取一个 Frame 的某个流组时会解码整个物理块。所以样本清单 `[3,1,3]`、逐对选样表 Q、Tx/Rx 子矩阵和显式收发对都不减少 I/O，只是内存中的挑选。在 0.2 中，这些选择又要和 poll/push、分析/Batch、调用级原子性与各语言绑定逐一组合验证，组合数随选择种类成倍增长。IO-01 在不同段落里时而写"批次"、时而写"调用级"。

## 决定

1. **Core I/O** 只交付：一个 Scan、一组 Frame（单帧或 Batch）、一个或多个流组的稠密样本、对应的有效性位图，以及帧位置与帧级附加记录。poll/push、分析/Batch、IO-01 原子性只作用于 Core I/O。
2. **选择层**：帧内的流、声束、Tx/Rx、收发对、样本窗口与有序清单是不做文件 I/O 的纯函数，作用于 Core I/O 结果，语义完全按 READ-02/FMC-02（保序保重复、交叉与配对分开、逐流边界检查）。A 扫读取也是选择层在单帧结果上的取用。
3. **IO-01 的作用单元**是每一次数据读写调用（单帧、Batch、A 扫都一样），而不是"批次"。

## 后果

- 选择语义的测试（UC-05、UC-07、UC-10～12）不再需要与 poll/push 组合，只需验证选择层与 Core I/O 结果的等价。
- A 扫随机读的代价由物理块大小决定，这一权衡在 D-04 中记录。
