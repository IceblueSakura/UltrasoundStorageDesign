# M1 实验：test-only 原型与机制取证

状态：草案阶段的临时 test-only 实验代码，对应 Spec `0.3-draft`；随设计调整可以重写或删除。不是 SDK，编码不是产品格式，结果见 [REPORT.md](REPORT.md)。

本目录用于 M1 阶段取证：以 [MAP-02](../../docs/DATA_SPEC.md#map-02) 的参考机制实现最小写入—封存—读取—恢复链路，检验 [WRT-01/02/03](../../docs/DATA_SPEC.md#wrt-01)、[IO-01](../../docs/DATA_SPEC.md#io-01)、[LIF-01/02](../../docs/DATA_SPEC.md#lif-01)、[BUF-01](../../docs/DATA_SPEC.md#buf-01) 与 [ADR-0004/0005](../../docs/decisions/README.md) 的可实现性。所有路径、记录布局和错误类都是实验约定，不能作为 D-07/D-10 的答案。

## 目录

| 路径 | 内容 |
|---|---|
| `ussproto/` | 原型：`writer.py`（只写一次的块、尾部日志、双槽提交记录、写失败态、故障点；Flush 只调用 `H5Fflush`，`os_sync=True` 另加 fsync，仅供对照）、`reader.py`（Core I/O、poll 借用、push 两阶段读、块几何查询 `layout()`、只读恢复，含在内存中清除状态标志的原地打开）、`select.py`（选择层）、`verify.py`（深度校验）、`codec.py`、`layout.py` |
| `tools/testdata_source.py` | 把 `testdata/scan.h5` 读成完整 Frame；不依赖 `ussproto`，同时充当独立期望值 |
| `tools/import_testdata.py` | 把导出数据写成一个 PA Scan 并封存 |
| `tools/check_independent.py` | 不导入 `ussproto` 的独立核对：按本文的布局说明解析，经 HDF5 自身的 filter 解码，重算全部校验值并与导出数据逐值比较；可在不同 HDF5 版本下运行 |
| `tests/` | 各项实验脚本（含 `bench_flush` 的 Flush 开销对照、`bench_pool_stream` 的固定内存池遍历），结果写入 `experiments/runs/m1-*/`（已忽略） |
| `probes/` | 评审阶段的 HDF5 行为探针（Flush 后崩溃、SWMR 多 Scan、只写一次 + 日志的雏形）；当时 flake 的 HDF5 缺 deflate，故使用 szip |
| `run.sh` | 构建所需环境并运行全部实验 |

## 运行

```sh
experiments/m1/run.sh                 # 全部实验
experiments/m1/run.sh test_crash      # 单项
```

`run.sh` 通过 `nix build` 取得 flake 的 Python/HDF5 2.2 环境、`h5clear`，以及 nixpkgs 默认 h5py（HDF5 1.14）用于可读性核对。测试数据路径默认 `testdata/scan.h5`，可用 `USS_TESTDATA` 覆盖。崩溃实验的帧数与轮数可用 `USS_CRASH_FRAMES`、`USS_CRASH_ITER` 调整。脚本一律以 `python -I` 运行。

## test-only 文件布局 `uss-m1-test-only` v0

文件以 libver `(v110, v114)` 写出（ADR-0005）。

```text
/                         attrs: uss_format, uss_format_version, spec_revision, workpiece_id, created_utc
/lifecycle  [1]           state(u1: 0 open / 1 sealed / 2 sealed_with_failure), n_scans, failure_*, record_crc
/scans/sNNNN/             attrs: scan_id
    definition            JSON 字节：groups[name, interpretation, K, S, dtype, codec, stream_table],
                          frames_per_chunk F, sums_rows_per_chunk Fs, frame_records.fields, metadata
    metadata/<name>       uint8 内容；attrs content_type, content_version
    g/<group>/samples     [E, K, S]，块 (F, K, S)，filter 链由 codec 声明
    g/<group>/valid       [E, ceil(K/8)] u1，位图按 little 位序打包，块 (F, ·)
    frames/records        [E] 复合类型（帧位置及其他帧级附加记录），块 (F,)
    sums                  [·] 每个数据块序号 c 一行：各对象第 c 块的 stored_len / stored_crc / decoded_crc
    journal/<object>      [2, F-1, ...] 连续存储，两槽尾部日志；journal/sums 为 [2, Fs-1]
    commit      [2]       seq, scan_state(0 active/1 complete), n_frames, data_chunks, sums_chunks,
                          sums_chain, tail_crc[对象], sums_tail_crc, record_crc
```

规则：

- 对象顺序为各组的 `samples`、`valid`，最后是 `frames/records`；`sums` 与 `commit` 中的数组按此顺序排列。
- 所有帧轴对象的块只经 `H5Dwrite_chunk` 写一次。extent `E` 只增长，是上界；可见范围只由提交记录决定（WRT-02）。Scan 完成时最后一个半满块补零后写一次。
- 选择 `seq` 最大且 `record_crc`（记录除最后 4 字节外的 CRC32）有效的提交记录。`active` 时，前 `data_chunks×F` 帧在主数据集，其余 `n_frames − data_chunks×F` 帧在 `journal/<object>[seq % 2]`；`complete` 时全部在主数据集。
- `sums` 的前 `sums_chunks×Fs` 行在主数据集（`complete` 时为前 `data_chunks` 行），其余在 `journal/sums[seq % 2]`；全部 `data_chunks` 行依次做 CRC32 链，结果须等于 `sums_chain`。
- 校验值算法为 CRC32（zlib）。正式算法属 D-07。
- codec：`none`、`deflate1`、`shuffle-deflate1`，都是 HDF5 标准 filter 链，任何 HDF5 读取器都能解码。

## 边界

- 只覆盖进程崩溃（SIGKILL 与故障点）；断电与操作系统崩溃不在范围（ADR-0008），也没有相关证据。`kill -9` 后页缓存仍会写回磁盘。
- 只在 Linux 上运行（本阶段范围）。原地恢复通过 ctypes 调用 h5py 所链接的 libhdf5，依赖 HDF5 私有的 fapl 属性 `clear_status_flags`。
- 读取器与独立核对出自同一作者，同一语言；后者只保证代码路径独立。
- 测试数据是临时导出的真实负载，只用于驱动实验，不作为设计参考；其压缩率与时序不代表目标设备。
