# ADR-0005：写出文件限定为 HDF5 1.10–1.14 可读的格式

- 状态：已采纳（2026-10-24，Spec 0.3-draft）；[ADR-0021](0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md) 保留 `v1.10–v1.14` 写出限制，但取消 HDF5 1.14 独立读取器双实现强制门禁。
- 规则落点：[DOC-01](../DATA_SPEC.md#doc-01)、[MAP-01](../DATA_SPEC.md#map-01)、D-07
- 仍未决定：具体标识、路径、字符串与位图编码（D-07）

## 背景

"固定 HDF5 2.x"没有区分 SDK 链接的库版本与写出文件的格式。HDF5 2.x 写出的某些对象，1.x 读不了：原生复数类（`H5T_COMPLEX`）、≥4 GiB 的 chunk，以及把 libver 下界设为 2.0 时启用的 4.0 格式变化。另一方面，SWMR 与 extensible array chunk 索引需要 ≥1.10 的格式（v3 superblock）。第三方工具（h5py、MATLAB、HDFView 等）可能仍链接 1.x。

## 决定

1. SDK 使用 HDF5 2.x 库实现，写出文件时把 libver 范围限定为 v1.10 至 v1.14，不使用 2.0 专有特性。
2. 复数样本若纳入支持，采用实部/虚部复合类型约定，不使用 `H5T_COMPLEX`。
3. 单个 chunk 小于 4 GiB。
4. 若将来确需 2.0 专有特性，必须新增能力声明，并在 D-07 中写明拒绝旧读取器的方式。

## 后果

- v3 superblock 的状态标志会让崩溃文件无法以普通方式只读打开，恢复按 [LIF-02](../DATA_SPEC.md#lif-02) 进行：在副本上或只在内存中清除状态标志，或走 SWMR 只读路径。
- 独立读取验证（T-22）至少在一个 1.14 系读取器上执行。
