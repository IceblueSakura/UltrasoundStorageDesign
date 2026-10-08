#!/usr/bin/env python3
"""Ultrasound Storage Benchmark for Single-Channel-Continuous Computations (Blosc2 & Native Bitshuffle).

Evaluates modern high-throughput compression codecs:
- Blosc2 + Bitshuffle + Zstandard (level 2) [HDF5 Filter ID 32026]
- Blosc2 + Bitshuffle + LZ4 [HDF5 Filter ID 32026]
- Blosc2 + Bitshuffle + BloscLZ [HDF5 Filter ID 32026]
- Native Bitshuffle + LZ4 [HDF5 Filter ID 32008]
- Native Bitshuffle + Zstandard (level 2) [HDF5 Filter ID 32008]
- Uncompressed baseline

Supports CTS and SPLIT architectures, u16/u32 data, multi-channel independent randomization,
and aggregation across multiple test repeats (median + spread).
"""
from __future__ import annotations
import argparse, csv, gc, json, os, platform, random, sys, time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import h5py
import numpy as np

try:
    import hdf5plugin
except ImportError:
    hdf5plugin = None

MIB = 1024**2


@dataclass(frozen=True)
class CandidateConfig:
    arch: str        # 'CTS', 'SPLIT', or 'TCS'
    name: str        # unique layout name
    chunk_t: int     # chunk size along Trigger dimension
    chunk_s: int     # chunk size along Sample dimension
    codec: str       # 'blosc2_zstd', 'blosc2_lz4', 'blosc2_blosclz', 'bitshuffle_lz4', 'bitshuffle_zstd', 'uncompressed'


def get_compressor_opts(codec: str) -> dict[str, Any]:
    if codec in ('none', 'uncompressed'):
        return {}
    if hdf5plugin is None:
        raise RuntimeError("hdf5plugin is required for compression codecs")
    
    if codec.startswith('blosc2_'):
        sub = codec[len('blosc2_'):]
        flt = hdf5plugin.Blosc2.BITSHUFFLE
        if 'delta_' in sub:
            flt = hdf5plugin.Blosc2.DELTA
            sub = sub.replace('delta_', '')
        elif sub == 'delta':
            flt = hdf5plugin.Blosc2.DELTA
            sub = 'zstd'
            
        if sub.startswith('zstd'):
            lvl = 2
            if '_l' in sub:
                try: lvl = int(sub.split('_l')[1])
                except ValueError: pass
            return hdf5plugin.Blosc2(cname='zstd', clevel=lvl, filters=flt)
        elif sub == 'lz4':
            return hdf5plugin.Blosc2(cname='lz4', clevel=5, filters=flt)
        elif sub == 'blosclz':
            return hdf5plugin.Blosc2(cname='blosclz', clevel=5, filters=flt)
        else:
            raise ValueError(f"Unknown Blosc2 codec variant: {codec}")
            
    elif codec == 'bitshuffle_lz4':
        return hdf5plugin.Bitshuffle(cname='lz4')
    elif codec.startswith('bitshuffle_zstd'):
        lvl = 2
        if '_l' in codec:
            try: lvl = int(codec.split('_l')[1])
            except ValueError: pass
        return hdf5plugin.Bitshuffle(cname='zstd', clevel=lvl)
    else:
        raise ValueError(f"Unknown codec: {codec}. (Blosc1 has been phased out, use blosc2_* or bitshuffle_*)")


def generate_independent_channel_rf(t_count: int, c_count: int, s_count: int, dtype_str: str, seed: int = 20261006) -> np.ndarray:
    """Generate realistic ultrasound RF signals with fully independent random data per channel."""
    is_u16 = (dtype_str == 'u16')
    dtype = np.uint16 if is_u16 else np.uint32
    max_val = 65535 if is_u16 else 4294967295
    baseline = 32768.0 if is_u16 else 8388608.0
    noise_std = 12.0 if is_u16 else 2000.0
    amp_max = 28000.0 if is_u16 else 6000000.0

    print(f"Generating independent random ultrasound RF [{t_count}, {c_count}, {s_count}] {dtype_str}...", flush=True)
    output = np.empty((t_count, c_count, s_count), dtype=dtype)
    t_axis = np.arange(s_count, dtype=np.float64)

    for ch in range(c_count):
        ch_seed = seed + ch * 10007 + s_count
        rng = np.random.default_rng(ch_seed)
        
        noise = rng.normal(0, noise_std, size=(t_count, s_count))
        rf = baseline + noise
        
        num_pulses = rng.integers(5, 9)
        f0 = rng.uniform(0.04, 0.06)
        sigma = max(8.0, float(s_count) / rng.uniform(80.0, 120.0))
        
        for _ in range(num_pulses):
            t0 = rng.integers(int(s_count * 0.05), int(s_count * 0.95), size=(t_count, 1))
            amp = rng.uniform(-amp_max, amp_max, size=(t_count, 1))
            dt = t_axis - t0
            wavelet = amp * np.exp(-0.5 * (dt / sigma)**2) * np.cos(2 * np.pi * f0 * dt)
            rf += wavelet
            
        output[:, ch, :] = np.clip(rf, 0, max_val).astype(dtype)

    return output


def compute_chunk_shapes(s_count: int, dtype_bytes: int, target_chunk_bytes: int = 512 * 1024) -> list[tuple[str, int, int]]:
    """Compute adaptive chunk sizes (chunk_t, chunk_s) based on sample length."""
    waveform_bytes = s_count * dtype_bytes
    
    # 1. Full waveform chunking: chunk_s = S
    chunk_t_full = max(1, min(4096, target_chunk_bytes // waveform_bytes))
    configs = [('full_waveform', chunk_t_full, s_count)]
    
    # 2. Sample-split chunking if S is large (> 1024)
    if s_count > 1024:
        split_s = 1024 if s_count <= 8192 else 2048
        chunk_t_split = max(1, min(4096, target_chunk_bytes // (split_s * dtype_bytes)))
        configs.append(('sample_chunk', chunk_t_split, split_s))
        
    return configs


class CompressedStore:
    def __init__(self, path: Path, cfg: CandidateConfig, c: int, s: int, mode: str,
                 cache_bytes: int, dtype: np.dtype):
        self.cfg, self.c, self.s = cfg, c, s
        self.dtype = dtype
        
        per_cache = max(64 * 1024, cache_bytes // (c if cfg.arch == 'SPLIT' else 1))
        self.f = h5py.File(path, mode, libver='latest', rdcc_nbytes=per_cache, rdcc_nslots=10007)
        self.ds: list[h5py.Dataset] = []
        
        if mode == 'w':
            self.f.attrs.update(
                format_name='ultrasound_compressed_benchmark_blosc2',
                arch=cfg.arch,
                layout_name=cfg.name,
                codec=cfg.codec,
                channel_count=c,
                sample_count=s,
                dtype=str(dtype)
            )
            
            c_opts = get_compressor_opts(cfg.codec)
            fill_val = 0
            if cfg.arch == 'CTS':
                chunks = (1, cfg.chunk_t, cfg.chunk_s)
                self.ds = [self.f.create_dataset(
                    'raw/samples',
                    shape=(c, 0, s),
                    maxshape=(c, None, s),
                    chunks=chunks,
                    dtype=dtype,
                    fillvalue=fill_val,
                    **c_opts
                )]
            elif cfg.arch == 'SPLIT':
                chunks = (cfg.chunk_t, cfg.chunk_s)
                self.ds = [self.f.create_dataset(
                    f'raw/channels/{i:04d}/samples',
                    shape=(0, s),
                    maxshape=(None, s),
                    chunks=chunks,
                    dtype=dtype,
                    fillvalue=fill_val,
                    **c_opts
                ) for i in range(c)]
            elif cfg.arch == 'TCS':
                chunks = (cfg.chunk_t, 1, cfg.chunk_s)
                self.ds = [self.f.create_dataset(
                    'raw/samples',
                    shape=(0, c, s),
                    maxshape=(None, c, s),
                    chunks=chunks,
                    dtype=dtype,
                    fillvalue=fill_val,
                    **c_opts
                )]
            else:
                raise ValueError(f"Unknown architecture: {cfg.arch}")
                
            self.status = self.f.create_dataset('records/status', shape=(0, c), maxshape=(None, c), chunks=(128, c), dtype='u1')
            self.commit = self.f.create_dataset('control/committed_count', data=np.uint64(0))
        else:
            if cfg.arch == 'SPLIT':
                self.ds = [self.f[f'raw/channels/{i:04d}/samples'] for i in range(c)]
            else:
                self.ds = [self.f['raw/samples']]
            self.status = self.f['records/status']
            self.commit = self.f['control/committed_count']

    def append_batch(self, x: np.ndarray, status: np.ndarray) -> None:
        """Append a buffered batch of shape [Batch, C, S]."""
        a = int(self.commit[()])
        b = a + x.shape[0]
        
        if self.cfg.arch == 'CTS':
            self.ds[0].resize(b, axis=1)
            self.ds[0][:, a:b, :] = np.ascontiguousarray(x.transpose(1, 0, 2))
        elif self.cfg.arch == 'SPLIT':
            for i, d in enumerate(self.ds):
                d.resize(b, axis=0)
                d[a:b, :] = np.ascontiguousarray(x[:, i, :])
        elif self.cfg.arch == 'TCS':
            self.ds[0].resize(b, axis=0)
            self.ds[0][a:b, :, :] = x

        self.status.resize(b, axis=0)
        self.status[a:b, :] = status
        self.f.flush()
        self.commit[()] = np.uint64(b)
        self.f.flush()

    def read_single_channel_batch(self, channel_idx: int, start: int, stop: int) -> np.ndarray:
        if self.cfg.arch == 'CTS':
            return self.ds[0][channel_idx, start:stop, :]
        elif self.cfg.arch == 'SPLIT':
            return self.ds[channel_idx][start:stop, :]
        else: # TCS
            return self.ds[0][start:stop, channel_idx, :]

    def read_single_channel_all(self, channel_idx: int) -> np.ndarray:
        if self.cfg.arch == 'CTS':
            return self.ds[0][channel_idx, :, :]
        elif self.cfg.arch == 'SPLIT':
            return self.ds[channel_idx][:, :]
        else: # TCS
            return self.ds[0][:, channel_idx, :]

    def read_single_channel_gate(self, channel_idx: int, gate: slice) -> np.ndarray:
        if self.cfg.arch == 'CTS':
            return self.ds[0][channel_idx, :, gate]
        elif self.cfg.arch == 'SPLIT':
            return self.ds[channel_idx][:, gate]
        else: # TCS
            return self.ds[0][:, channel_idx, gate]

    def close(self) -> None:
        self.f.close()


def summarize(values: list[float]) -> dict[str, float]:
    a = np.array(values, dtype=np.float64)
    return {
        'n': len(values),
        'median_ms': float(np.median(a) * 1000.0),
        'p95_ms': float(np.quantile(a, 0.95) * 1000.0),
        'min_ms': float(a.min() * 1000.0),
        'max_ms': float(a.max() * 1000.0)
    }


def verify_integrity(store: CompressedStore, data_tcs: np.ndarray, status: np.ndarray) -> None:
    t, c, s = data_tcs.shape
    for ch in range(c):
        got = store.read_single_channel_all(ch)
        expected = data_tcs[:, ch, :]
        if not np.array_equal(got, expected):
            raise AssertionError(f"Decompressed data mismatch on channel {ch}!")
    if not np.array_equal(store.status[:], status):
        raise AssertionError("Status array mismatch!")


def run_workloads(store: CompressedStore, data_tcs: np.ndarray, args: argparse.Namespace) -> dict[str, Any]:
    t, c, s = data_tcs.shape
    rng = np.random.default_rng(args.seed + 101)
    results = {}
    
    # 1. Single channel batch read
    batch_size = min(args.read_batch, t)
    query_count = args.queries
    times_w1, bytes_w1 = [], []
    for _ in range(query_count):
        ch = int(rng.integers(c))
        start = int(rng.integers(0, t - batch_size + 1))
        t0 = time.perf_counter()
        arr = store.read_single_channel_batch(ch, start, start + batch_size)
        elapsed = time.perf_counter() - t0
        times_w1.append(elapsed)
        bytes_w1.append(arr.nbytes)
    res_w1 = summarize(times_w1)
    res_w1['logical_MiB_s'] = float(sum(bytes_w1) / MIB / sum(times_w1))
    results['single_channel_batch_read'] = res_w1

    # 2. Single channel all-triggers read
    times_w2, bytes_w2 = [], []
    for _ in range(max(4, c)):
        ch = int(rng.integers(c))
        t0 = time.perf_counter()
        arr = store.read_single_channel_all(ch)
        elapsed = time.perf_counter() - t0
        times_w2.append(elapsed)
        bytes_w2.append(arr.nbytes)
    res_w2 = summarize(times_w2)
    res_w2['logical_MiB_s'] = float(sum(bytes_w2) / MIB / sum(times_w2))
    results['single_channel_all_read'] = res_w2

    # 3. Single channel gate read
    gate_len = min(256, max(64, s // 8))
    gate_start = s // 4
    gate = slice(gate_start, gate_start + gate_len)
    times_w3, bytes_w3 = [], []
    for _ in range(max(4, c)):
        ch = int(rng.integers(c))
        t0 = time.perf_counter()
        arr = store.read_single_channel_gate(ch, gate)
        elapsed = time.perf_counter() - t0
        times_w3.append(elapsed)
        bytes_w3.append(arr.nbytes)
    res_w3 = summarize(times_w3)
    res_w3['logical_MiB_s'] = float(sum(bytes_w3) / MIB / sum(times_w3))
    results['single_channel_gate_read'] = res_w3

    # 4. Iterate all channels isolated
    times_w4 = []
    for _ in range(max(3, args.repeats)):
        t0 = time.perf_counter()
        for ch in range(c):
            _ = store.read_single_channel_all(ch)
        elapsed = time.perf_counter() - t0
        times_w4.append(elapsed)
    res_w4 = summarize(times_w4)
    res_w4['total_logical_MiB_s'] = float(data_tcs.nbytes / MIB / np.median(times_w4))
    results['iterate_all_channels_isolated'] = res_w4

    return results


def run_benchmark_for_sample_size(s: int, args: argparse.Namespace) -> dict[str, Any]:
    t = args.triggers
    c = args.channels
    dtype_str = args.dtype
    dtype = np.uint16 if dtype_str == 'u16' else np.uint32
    dtype_bytes = 2 if dtype_str == 'u16' else 4

    print(f"\n========================================================")
    print(f"BENCHMARK: T={t}, C={c} (Independent Random), S={s}, dtype={dtype_str} ({dtype_bytes}B)")
    print(f"Raw data volume: {(t * c * s * dtype_bytes) / MIB:.2f} MiB")
    print(f"========================================================", flush=True)

    data_tcs = generate_independent_channel_rf(t, c, s, dtype_str, seed=args.seed)
    status = np.full((t, c), 3, dtype='u1')
    raw_nbytes = data_tcs.nbytes

    chunk_schemes = compute_chunk_shapes(s, dtype_bytes, target_chunk_bytes=args.target_chunk_kib * 1024)
    target_archs = [x.upper().strip() for x in args.architectures.split(',')]
    codec_list = [x.strip() for x in args.codecs.split(',') if x.strip()]

    candidates: list[CandidateConfig] = []
    for arch in target_archs:
        for scheme_name, chunk_t, chunk_s in chunk_schemes:
            for codec in codec_list:
                name = f"{arch.lower()}_{scheme_name}_{codec}"
                candidates.append(CandidateConfig(
                    arch=arch,
                    name=name,
                    chunk_t=chunk_t,
                    chunk_s=chunk_s,
                    codec=codec
                ))

    results_by_candidate = {}
    for cfg in candidates:
        print(f"Testing: {cfg.name} (Arch={cfg.arch}, Chunk=[{cfg.chunk_t}, {cfg.chunk_s}], Codec={cfg.codec})...", flush=True)
        path = args.out / f"{cfg.name}_S{s}.h5"
        
        # Multi-repeat write benchmark (homologous aggregation / 同类项合并)
        write_times = []
        file_sizes = []
        for rep in range(args.repeats):
            store = CompressedStore(path, cfg, c, s, 'w', args.cache_mib * MIB, dtype)
            t0 = time.perf_counter()
            for a in range(0, t, args.write_batch):
                b = min(a + args.write_batch, t)
                store.append_batch(data_tcs[a:b], status[a:b])
            store.close()
            write_times.append(time.perf_counter() - t0)
            file_sizes.append(path.stat().st_size)

        file_size_median = int(np.median(file_sizes))
        comp_ratio = float(raw_nbytes / file_size_median) if file_size_median > 0 else 0.0
        write_speed = float(raw_nbytes / MIB / np.median(write_times))

        print(f"  -> Write Speed: {write_speed:6.1f} MiB/s (median of {args.repeats}), Size: {file_size_median/MIB:6.2f} MiB, Ratio: {comp_ratio:4.2f}x", flush=True)

        # Integrity check
        read_store = CompressedStore(path, cfg, c, s, 'r', args.cache_mib * MIB, dtype)
        verify_integrity(read_store, data_tcs, status)

        # Read workloads
        workload_res = run_workloads(read_store, data_tcs, args)
        read_store.close()

        rec = {
            'config': asdict(cfg),
            'sample_count': s,
            'channel_count': c,
            'trigger_count': t,
            'dtype': dtype_str,
            'raw_bytes': raw_nbytes,
            'compressed_file_bytes': file_size_median,
            'compression_ratio': comp_ratio,
            'write_repeats': args.repeats,
            'write_seconds_samples': write_times,
            'write_seconds_median': float(np.median(write_times)),
            'write_logical_MiB_s': write_speed,
            'workloads': workload_res
        }
        results_by_candidate[cfg.name] = rec

        if not args.keep_files:
            try: path.unlink()
            except OSError: pass
        gc.collect()

    return results_by_candidate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=Path('benchmark_results'))
    p.add_argument('--samples', type=str, default='2048,8192',
                   help='Comma-separated list of sample points S, e.g. "512,2048,8192,32768"')
    p.add_argument('--triggers', type=int, default=1024, help='Number of triggers T')
    p.add_argument('--channels', type=int, default=4, help='Number of channels C (default 4)')
    p.add_argument('--dtype', choices=['u16', 'u32'], default='u16', help='Sample data type')
    p.add_argument('--write-batch', type=int, default=64, help='Buffer append batch size')
    p.add_argument('--read-batch', type=int, default=64, help='Single channel batch read size')
    p.add_argument('--codecs', type=str,
                   default='blosc2_lz4,blosc2_zstd,blosc2_delta_zstd,blosc2_delta_lz4,bitshuffle_lz4,bitshuffle_zstd,uncompressed',
                   help='Comma-separated codecs: blosc2_lz4,blosc2_zstd,blosc2_delta_zstd,blosc2_delta_lz4,bitshuffle_lz4,bitshuffle_zstd,uncompressed')
    p.add_argument('--architectures', type=str, default='CTS,SPLIT',
                   help='Comma-separated architectures to benchmark: CTS,SPLIT,TCS')
    p.add_argument('--target-chunk-kib', type=int, default=512, help='Target chunk size in KiB')
    p.add_argument('--cache-mib', type=int, default=16, help='HDF5 raw chunk cache budget in MiB')
    p.add_argument('--repeats', type=int, default=3, help='Number of repeats for homologous aggregation (同类项合并取中位数)')
    p.add_argument('--queries', type=int, default=32, help='Repeats for read queries')
    p.add_argument('--keep-files', action='store_true', help='Keep generated H5 files')
    p.add_argument('--overwrite', action='store_true', help='Overwrite existing output dir')
    p.add_argument('--seed', type=int, default=20261006)
    args = p.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    sample_list = [int(x.strip()) for x in args.samples.split(',') if x.strip()]
    for s in sample_list:
        if s < 64 or s > 131072:
            p.error(f"Sample size S={s} out of reasonable range [64, 131072]")

    all_results = {
        'suite': 'ultrasound_storage_blosc2_and_bitshuffle_benchmark_v2',
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'platform': platform.platform(),
        'python': sys.version,
        'h5py': h5py.__version__,
        'hdf5plugin': getattr(hdf5plugin, 'version', 'unavailable') if hdf5plugin else 'none',
        'args': vars(args),
        'results_by_sample_size': {}
    }

    summary_rows = []
    summary_header = [
        'sample_count', 'arch', 'chunk_scheme', 'codec', 'dtype',
        'comp_ratio', 'write_MiB_s', 'batch_read_ms', 'batch_read_MiB_s',
        'all_read_ms', 'all_read_MiB_s', 'gate_read_ms', 'iterate_all_ms'
    ]

    for s in sample_list:
        res_s = run_benchmark_for_sample_size(s, args)
        all_results['results_by_sample_size'][str(s)] = res_s
        
        for cand_name, rec in res_s.items():
            cfg = rec['config']
            w = rec['workloads']
            row = [
                s,
                cfg['arch'],
                'full' if cfg['chunk_s'] == s else 'split',
                cfg['codec'],
                rec['dtype'],
                f"{rec['compression_ratio']:.2f}",
                f"{rec['write_logical_MiB_s']:.1f}",
                f"{w['single_channel_batch_read']['median_ms']:.3f}",
                f"{w['single_channel_batch_read']['logical_MiB_s']:.1f}",
                f"{w['single_channel_all_read']['median_ms']:.3f}",
                f"{w['single_channel_all_read']['logical_MiB_s']:.1f}",
                f"{w['single_channel_gate_read']['median_ms']:.3f}",
                f"{w['iterate_all_channels_isolated']['median_ms']:.2f}"
            ]
            summary_rows.append(row)

    json_path = args.out / 'results.json'
    csv_path = args.out / 'summary.csv'
    
    clean_dict = json.loads(json.dumps(all_results, default=str))
    json_path.write_text(json.dumps(clean_dict, indent=2, ensure_ascii=False), encoding='utf-8')

    with csv_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(summary_header)
        writer.writerows(summary_rows)

    print(f"\nBenchmark completed successfully!")
    print(f"Results saved to: {json_path}")
    print(f"Summary table saved to: {csv_path}")


if __name__ == '__main__':
    main()
