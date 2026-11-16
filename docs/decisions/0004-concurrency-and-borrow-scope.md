# ADR-0004：并发范围与 poll 借用的结束条件

- 状态：已采纳（2026-10-24，Spec 0.3-draft）
- 规则落点：[CORE-01](../DATA_SPEC.md#core-01)、[BUF-01](../DATA_SPEC.md#buf-01)；需求 [R-14](../DESIGN.md#r-14)
- 仍未决定：各绑定的受检视图、GC 与关闭行为（D-12）
- 补充：[ADR-0009](0009-review-contract-clarifications.md) 要求 SDK 自行检测并拒绝同一文件上的 Writer 与 Reader

## 背景

0.2 的"单读单写、无并发 Reader"没有说明作用域：按对象、文件、线程还是进程计？项目 flake 中的 HDF5 以 `HDF5_ENABLE_THREADSAFE=FALSE` 构建，同一进程两个线程哪怕访问不同文件也不安全。poll 视图的失效条件在 DESIGN、README 与 BUF-01 中写法不一致，容量查询等调用是否结束借用也没有规定。

## 决定

1. **进程内**：SDK 对所有 HDF5 调用做全局串行化（与文件无关），编解码可以在锁外并行。对外不承诺对象级线程安全：同一个 Reader 或 Writer 不得被并发调用。
2. **对象数量**：一个进程可以同时持有多个 Reader（访问同一或不同已封存文件），各自的 poll 借用独立。同一文件不能同时有 Writer 和 Reader；一个文件同一时刻只有一个 Writer。
3. **跨进程**：多个进程可以同时只读同一个已封存文件（HDF5 支持共享只读）。写入期间不支持其他进程读取。
4. **poll 借用结束条件**：同一 Reader 上任何交付样本数据的读取调用（poll 或 push，无论成功、失败还是被参数校验拒绝）在开始时结束先前的 poll 借用；Reader 关闭也会结束借用。目录、固定定义、元信息与容量查询不结束借用。
5. **GPU 流水线**：单个 Reader 同一时刻只有一份 poll 视图；双缓冲流水线应使用 push，或者使用两个 Reader。

## 后果

- 新增 T-24 追踪 R-14：跨线程串行化、多 Reader 借用独立、多进程只读、借用结束条件。
- .NET Framework 单个 byte 数组最多 2,147,483,591 字节（即使开启 `gcAllowVeryLargeObjects`），Span 长度为 int：超过这一规模的 Batch 只能走非托管内存，记入 D-12。
- Python 绑定的 poll 可以借鉴 `bytearray`：若上一份视图仍有导出（例如 numpy 视图），下一次读取抛出 `BufferError`，而不是暗中复制来延长寿命。是否采用属于 D-12。
