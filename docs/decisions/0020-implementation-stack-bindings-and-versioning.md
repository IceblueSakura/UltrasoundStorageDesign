# ADR-0020：原生技术栈、静态自包含分发、首版 .NET 绑定与 1.0 兼容门禁

- 状态：已采纳（2026-11-27）；[ADR-0021](0021-hdf5-simplification-wal-push-only-and-ndt-fixes.md) 补充跨平台 HDF5 硬加固（`H5dont_atexit`/`H5PLset_loading_state(0)`/低 `glibc`/`/MT`）、将 Windows + `.NET 4.8` 烟雾闭环前移至 M2，并推迟 `abidiff`/SONAME 至 `1.0-rc`。
- 规则落点：[API-01](../DATA_SPEC.md#api-01)、[SDK_CONTRACT.md](../SDK_CONTRACT.md)；细化 [ADR-0010](0010-public-api-stability.md)，收口 `D-12` 与版本兼容策略。
- 来源：用户在 `ADR-0010` 基础上对实现语言、绑定交付顺序、打包形态与版本演进的拍板（2026-11-27）。

## 背景

[ADR-0010](0010-public-api-stability.md) 确立了 C ABI 作为唯一稳定边界的四项原则，但尚未确定原生实现语言、原生库对 HDF5/压缩库的链接分发形态、多消费端（`.NET 10`、`.NET Framework 4.8`、Python）的交付优先级，以及文件格式版本与 C ABI 兼容性的冻结起点和门禁。

## 决定

1. **原生实现语言：C++20 核心引擎 + 纯 C11 头文件导出稳定 C ABI。**
   - 核心引擎使用 C++20 实现，利用 RAII 严格管理 HDF5 `hid_t` 句柄、进程内全局 HDF5 串行互斥锁与块缓存生命周期；与 HDF5 2.x、`libzstd`、`liblz4`、`xxhash` 零 FFI 摩擦，CMake/Ninja + Nix/MSVC 跨平台构建成熟。
   - 公开头文件严格为纯 C11（不暴露任何 HDF5、C++ 标准库或异常类型），全部 `extern "C"` 导出函数内部全捕获异常并映射为稳定错误码与提交状态（落实 `ADR-0010`）。
2. **原生库采用单库静态自包含分发。**
   - 交付产物（Linux `libuss.so` / Windows `uss.dll`）静态链接 HDF5 2.x（`v1.10–v1.14` 写出模式）、`libzstd`、`liblz4` 与 `xxhash`，对外仅导出 `uss_*` 公开 C ABI 符号（隐藏内部第三方符号），彻底杜绝现场工控机及 Windows `.NET 4.8` 环境中的 HDF5/压缩库 DLL 版本冲突。
3. **首版（M3）聚焦 C ABI + `.NET` 绑定，Python 官方绑定延后至 M4。**
   - 首版（M3）优先服务 UMS 与 Windows 工业消费端，交付 **C ABI 原生库 + 单一多目标 `.NET` 绑定库（`net10.0` + `net48`，x64）**：通过 P/Invoke 仅调用 C ABI，使用 `SafeHandle` 管理不透明句柄寿命，通过非托管内存接口支撑超过 2 GiB 的 `push` Batch（适配 UMS `Batch-of-SoA` 并突破 `.NET Framework 4.8` 托管数组上限），使用代数令牌（generation token）提供受检 `poll` 视图以防悬垂访问。
   - 验证顺序维持“先在 Linux x64 完成 M2/M3 闭环，再补 Windows 10+ x64 MSVC 与 `.NET Framework 4.8` 实测”。
   - **Python 官方绑定延后至 M4**（M2/M3 测试与核对脚本允许使用临时 `ctypes` 封装，不构成产品绑定交付承诺）。
4. **版本彻底解耦与 `1.0` 冻结门禁。**
   - **三套版本独立演进**：文件容器格式版本（`format_major.format_minor`）、各扫描模式独立 Schema 版本（`schema_major.schema_minor`）与 SDK 库版本（SemVer `lib_major.lib_minor.lib_patch`）互不绑定。同一 `format_major` 下新 `minor` 仅允许向后兼容扩展或显式标注 `ID-02` 必要能力标志；未知 `format_major` 或未知必要能力必须拒绝。
   - **`0.x` 演进、`1.0` 冻结**：`0.x` 阶段（M2/M3 与 UMS 早期联调）允许受控破坏性调整并随变更推进文档与 Spec；自 `1.0.0` 起冻结 C ABI 与文件格式 `1.0`，整个 `1.x` 周期维持二进制向后兼容——Linux 启用 SONAME、版本脚本（`USS_1.0`）与 CI `abidiff` 门禁，Windows 维护固定导出表，并提供运行时版本与能力查询接口（支持模式 Schema、内置 codec、未来可选 GPU 能力）。

## 理由

- 静态自包含单库是跨 Linux LTS 与 Windows `.NET 4.8` 工控环境落地最稳妥的分发形态，尤其在已内置精简 codec（`zstd`/`lz4`）后可保证任意部署环境“装即能读”。
- 首版砍掉正式 Python 绑定维护矩阵，将工程火力集中在 C++20 Core 与 UMS 直接消费的 `.NET` 绑定上，显著降低 M3 交付风险。
- 允许 `0.x` 在真实 UMS 联调中磨合签名，再于 `1.0` 启用硬性 `abidiff` 门禁，兼顾早期敏捷性与长期开源兼容信誉。

## 后果与未决项

- `D-12` 首版技术路线完全闭合（剩余仅精确 OS 发行版/编译器下限矩阵与 Windows M3 实测验证；Python 官方绑定归 M4）。
- 详细 ABI 工程规格、绑定安全约束与打包要求统一归位至新建的 [SDK_CONTRACT.md](../SDK_CONTRACT.md)。
