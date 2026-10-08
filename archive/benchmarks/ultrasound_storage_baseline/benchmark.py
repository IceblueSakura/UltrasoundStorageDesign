#!/usr/bin/env python3
"""HDF5 waveform layout microbenchmark, not a production ultrasound SDK.

All candidates store identical fixed-length int16 samples, accept TCS input,
and return identical selections. No image formation, quality filtering, or
calibration is performed. Write timing includes repacking, resize and HDF5
flush but NOT fsync/durable media confirmation. Read tests are warm-cache.
"""
from __future__ import annotations
import argparse, csv, gc, hashlib, json, os, platform, random, subprocess, sys, time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import h5py
import numpy as np

MIB = 1024**2

@dataclass(frozen=True)
class Layout:
    name: str
    order: str
    bt: int
    bc: int
    bs: int


def layouts(c: int, s: int) -> list[Layout]:
    return [
        Layout('tcs_frame_chunk', 'TCS', 16, c, s),
        Layout('tcs_channel_chunk', 'TCS', 128, 1, s),
        Layout('cts_channel_chunk', 'CTS', 128, 1, s),
        Layout('split_full_128', 'SPLIT', 128, 1, s),
        Layout('split_full_16', 'SPLIT', 16, 1, s),
        Layout('split_sample_256', 'SPLIT', 128, 1, min(256,s)),
    ]


def check_batch(x: np.ndarray, status: np.ndarray, c: int, s: int) -> None:
    """Reject before any dataset extent change. Invalid flags do not waive shape."""
    if not isinstance(x,np.ndarray) or x.ndim!=3 or x.shape[1:]!=(c,s) or x.shape[0]<1:
        raise ValueError('batch must have exact shape [positive_count, channel_count, sample_count]')
    if x.dtype != np.dtype('<i2'):
        raise TypeError('exact int16 dtype required; no silent cast')
    if status.dtype!=np.dtype('u1') or status.shape!=x.shape[:2]:
        raise ValueError('status must be uint8 [count,channel_count]')
    if np.any(~np.isin(status,[1,3])):
        raise ValueError('this dense benchmark only accepts present-invalid=1 or present-valid=3')


class Store:
    def __init__(self, path: Path, layout: Layout, c: int, s: int, mode: str, cache: int,
                 compression: str|None=None):
        self.layout,self.c,self.s = layout,c,s
        # HDF5 raw chunk cache is per dataset; split candidates divide the budget.
        per=max(1024,cache//(c if layout.order=='SPLIT' else 1))
        self.f=h5py.File(path,mode,libver='latest',rdcc_nbytes=per,rdcc_nslots=10007)
        self.ds=[]
        if mode=='w':
            self.f.attrs.update(format_name='ultrasound_layout_microbenchmark',schema_version='experiment-1',
                                profile_id='conventional_uniform',layout_id=layout.name,
                                synthetic=True,sample_count=s,channel_count=c)
            opts=dict(dtype='<i2',compression=compression,shuffle=bool(compression),fillvalue=0)
            if layout.order=='TCS':
                self.ds=[self.f.create_dataset('raw/samples',shape=(0,c,s),maxshape=(None,c,s),
                    chunks=(layout.bt,layout.bc,layout.bs),**opts)]
            elif layout.order=='CTS':
                self.ds=[self.f.create_dataset('raw/samples',shape=(c,0,s),maxshape=(c,None,s),
                    chunks=(layout.bc,layout.bt,layout.bs),**opts)]
            else:
                self.ds=[self.f.create_dataset(f'raw/channels/{i:04d}/samples',shape=(0,s),maxshape=(None,s),
                    chunks=(layout.bt,layout.bs),**opts) for i in range(c)]
            self.status=self.f.create_dataset('records/status',shape=(0,c),maxshape=(None,c),chunks=(128,c),dtype='u1')
            self.config=self.f.create_dataset('records/config_index',shape=(0,),maxshape=(None,),chunks=(128,),dtype='<u4')
            self.commit=self.f.create_dataset('control/committed_count',data=np.uint64(0))
        else:
            self.ds=([self.f['raw/samples']] if layout.order!='SPLIT' else
                     [self.f[f'raw/channels/{i:04d}/samples'] for i in range(c)])
            self.status=self.f['records/status'];self.config=self.f['records/config_index'];self.commit=self.f['control/committed_count']

    def append(self,x:np.ndarray,status:np.ndarray)->None:
        check_batch(x,status,self.c,self.s)
        a=int(self.commit[()]); b=a+x.shape[0]
        if self.layout.order=='TCS':
            self.ds[0].resize(b,axis=0);self.ds[0][a:b,:,:]=x
        elif self.layout.order=='CTS':
            self.ds[0].resize(b,axis=1)
            self.ds[0][:,a:b,:]=np.ascontiguousarray(x.transpose(1,0,2))
        else:
            for i,d in enumerate(self.ds):
                d.resize(b,axis=0);d[a:b,:]=np.ascontiguousarray(x[:,i,:])
        self.status.resize(b,axis=0);self.status[a:b,:]=status
        self.config.resize(b,axis=0);self.config[a:b]=0
        self.f.flush()
        self.commit[()]=np.uint64(b)
        self.f.flush()

    def read_channel(self,t: int|slice,c:int,g:slice=slice(None))->np.ndarray:
        if self.layout.order=='TCS': return self.ds[0][t,c,g]
        if self.layout.order=='CTS': return self.ds[0][c,t,g]
        return self.ds[c][t,g]

    def read_tcs_into(self,start:int,stop:int,out:np.ndarray,scratch:np.ndarray)->None:
        """All layouts deliver identical C-contiguous [B,C,S]; pack time included."""
        b=stop-start
        if out.shape!=(b,self.c,self.s) or not out.flags.c_contiguous:
            raise ValueError('exact writable contiguous TCS destination required')
        if self.layout.order=='TCS':
            self.ds[0].read_direct(out,source_sel=np.s_[start:stop,:,:])
        elif self.layout.order=='CTS':
            self.ds[0].read_direct(scratch,source_sel=np.s_[:,start:stop,:])
            np.copyto(out,scratch.transpose(1,0,2))
        else:
            for i,d in enumerate(self.ds): d.read_direct(scratch[i],source_sel=np.s_[start:stop,:])
            np.copyto(out,scratch.transpose(1,0,2))

    def close(self)->None: self.f.close()


def env()->dict[str,Any]:
    d=dict(python=sys.version,numpy=np.__version__,h5py=h5py.__version__,hdf5=h5py.version.hdf5_version,
           platform=platform.platform(),cpu_count=os.cpu_count())
    try:
        import psutil
        d['memory_available_bytes']=psutil.virtual_memory().available
        d['rss_initial_bytes']=psutil.Process().memory_info().rss
    except ImportError: pass
    for p,k in [('/sys/fs/cgroup/memory.max','cgroup_memory_max'),('/sys/fs/cgroup/cpu.max','cgroup_cpu_max')]:
        try:d[k]=Path(p).read_text().strip()
        except OSError:pass
    try:
        d['cpu_model']=next(x.split(':',1)[1].strip() for x in Path('/proc/cpuinfo').read_text().splitlines() if x.startswith('model name'))
    except (OSError,StopIteration):pass
    try:d['filesystem']=subprocess.check_output(['findmnt','-T',str(Path.cwd()),'-n','-o','FSTYPE'],text=True).strip()
    except Exception:pass
    try:
        import torch
        d['torch']=torch.__version__;d['cuda_available']=bool(torch.cuda.is_available())
        if d['cuda_available']:d['gpu_name']=torch.cuda.get_device_name(0)
    except ImportError:d['cuda_available']=False;d['torch']=None
    return d


def summarize(values:list[float])->dict[str,float]:
    a=np.array(values,dtype=np.float64)
    return {'n':len(values),'median_ms':float(np.median(a)*1000),'p95_ms':float(np.quantile(a,.95)*1000),
            'min_ms':float(a.min()*1000),'max_ms':float(a.max()*1000)}


def negative_checks(store:Store,data:np.ndarray,status:np.ndarray)->list[str]:
    old=int(store.commit[()]);old_shapes=[d.shape for d in store.ds]
    cases=[('short_waveform',data[:1,:,:-1],status[:1]),
           ('long_waveform',np.pad(data[:1],((0,0),(0,0),(0,1))),status[:1]),
           ('wrong_dtype',data[:1].astype(np.float32),status[:1]),
           ('wrong_channel_count',data[:1,:-1],status[:1,:-1]),
           ('short_even_when_invalid',data[:1,:,:-1],np.ones_like(status[:1]))]
    passed=[]
    for name,x,m in cases:
        try:store.append(x,m)
        except (ValueError,TypeError):
            if int(store.commit[()])!=old or [d.shape for d in store.ds]!=old_shapes:
                raise AssertionError('rejected write changed physical extent or commit')
            passed.append(name)
        else:raise AssertionError('invalid write accepted: '+name)
    return passed


def verify(store:Store,data:np.ndarray,status:np.ndarray,batch:int)->dict[str,Any]:
    n,c,s=data.shape;h=hashlib.sha256()
    for a in range(0,n,batch):
        b=min(a+batch,n);out=np.empty((b-a,c,s),dtype='<i2');scratch=np.empty((c,b-a,s),dtype='<i2')
        store.read_tcs_into(a,b,out,scratch)
        if not np.array_equal(out,data[a:b]):raise AssertionError('waveform roundtrip mismatch')
        h.update(out.tobytes())
    if not np.array_equal(store.status[:],status):raise AssertionError('status mismatch')
    if int(store.commit[()])!=n:raise AssertionError('commit mismatch')
    if not np.all(store.config[:]==0):raise AssertionError('config mismatch')
    return {'roundtrip_all_samples':'PASS','status_roundtrip':'PASS','invalid_payload_preserved':'PASS',
            'committed_count':n,'waveform_sha256':h.hexdigest()}


def run_reads(store:Store,data:np.ndarray,args:argparse.Namespace)->dict[str,Any]:
    n,c,s=data.shape;rng=np.random.default_rng(args.seed+99);gate=slice(s//3,s//3+min(64,s-s//3))
    out=np.empty((args.read_batch,c,s),dtype='<i2');scratch=np.empty((c,args.read_batch,s),dtype='<i2')
    # Warm-up for OS pages and application stack. OS caches are never dropped.
    for a in range(0,n,args.read_batch):
        b=min(a+args.read_batch,n)
        if b-a==args.read_batch:store.read_tcs_into(a,b,out,scratch)
    jobs={
      'A_one_channel': [(int(rng.integers(n)),int(rng.integers(c))) for _ in range(args.queries)],
      'B_row_one_channel':[(int(rng.integers(args.rows)),int(rng.integers(c))) for _ in range(max(8,args.queries//4))],
      'D_col_hyperslab':[(int(rng.integers(args.cols)),int(rng.integers(c))) for _ in range(max(8,args.queries//4))],
      'D_col_gather':[],
      'C_gate_input_only':[(0,int(rng.integers(c))) for _ in range(4)],
      'stream_TCS_host_buffer':[(int(a),0) for a in np.arange(0,n-args.read_batch+1,args.read_batch)],
    }
    jobs['D_col_gather']=list(jobs['D_col_hyperslab'])
    ans={}
    # Shuffle operation order per layout; requests themselves are identical.
    kinds=list(jobs);random.Random(args.seed+sum(map(ord,store.layout.name))).shuffle(kinds)
    for kind in kinds:
        times=[];bytes_each=[]
        for rep in range(args.read_repeats):
            for x,ch in jobs[kind]:
                t0=time.perf_counter()
                if kind=='A_one_channel':got=store.read_channel(x,ch);expected=data[x,ch]
                elif kind=='B_row_one_channel':
                    sel=slice(x*args.cols,(x+1)*args.cols);got=store.read_channel(sel,ch);expected=data[sel,ch]
                elif kind=='D_col_hyperslab':
                    sel=slice(x,n,args.cols);got=store.read_channel(sel,ch);expected=data[sel,ch]
                elif kind=='D_col_gather':
                    # Reference alternative: contiguous waveform reads + stack, not a fused SDK optimization.
                    got=np.stack([store.read_channel(t,ch) for t in range(x,n,args.cols)]);expected=data[x:n:args.cols,ch]
                elif kind=='C_gate_input_only':
                    got=store.read_channel(slice(0,n),ch,gate);expected=data[:,ch,gate]
                else:
                    store.read_tcs_into(x,x+args.read_batch,out,scratch);got=out;expected=data[x:x+args.read_batch]
                elapsed=time.perf_counter()-t0
                # Correctness outside timer. It affects cache state, disclosed in the report.
                if not np.array_equal(got,expected):raise AssertionError('selection mismatch: '+kind)
                times.append(elapsed);bytes_each.append(got.nbytes)
        rec=summarize(times);rec['logical_bytes_per_request']=bytes_each[0]
        rec['logical_MiB_s']=float(sum(bytes_each)/MIB/sum(times))
        rec['raw_seconds']=times;rec['correctness']='PASS';ans[kind]=rec
    return ans


def run_gpu(store:Store,args:argparse.Namespace)->dict[str,Any]:
    if not args.gpu:return {'status':'NOT_RUN','reason':'--gpu not requested; CPU buffer benchmark is not GPU throughput'}
    try:import torch
    except ImportError:return {'status':'NOT_RUN','reason':'torch not installed'}
    if not torch.cuda.is_available():return {'status':'NOT_RUN','reason':'CUDA GPU unavailable'}
    b,c,s=args.read_batch,store.c,store.s
    host=torch.empty((b,c,s),dtype=torch.int16,pin_memory=True)
    dest=torch.empty((b,c,s),dtype=torch.int16,device='cuda')
    np_host=host.numpy();scratch=np.empty((c,b,s),dtype='<i2')
    read_times=[];copy_times=[];total_times=[]
    n=int(store.commit[()]);starts=list(range(0,n-b+1,b))
    for warm in range(2):
        store.read_tcs_into(0,b,np_host,scratch);dest.copy_(host,non_blocking=True);torch.cuda.synchronize()
    for start in starts:
        t0=time.perf_counter();store.read_tcs_into(start,start+b,np_host,scratch);t1=time.perf_counter()
        # Synchronization measures completed H2D, NOT merely asynchronous enqueue time.
        dest.copy_(host,non_blocking=True);torch.cuda.synchronize();t2=time.perf_counter()
        if not np.array_equal(dest.cpu().numpy(),np_host):raise AssertionError('GPU roundtrip mismatch')
        read_times.append(t1-t0);copy_times.append(t2-t1);total_times.append(t2-t0)
    return {'status':'RUN','mode':'serial pinned-host H2D; no overlap; no kernel; no GPUDirect',
            'read_pack':summarize(read_times),'h2d_completed':summarize(copy_times),'total':summarize(total_times),
            'total_logical_MiB_s':len(starts)*host.numel()*host.element_size()/MIB/sum(total_times)}


def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=Path('results'))
    p.add_argument('--rows',type=int,default=32);p.add_argument('--cols',type=int,default=128)
    p.add_argument('--channels',type=int,default=8);p.add_argument('--samples',type=int,default=2048)
    p.add_argument('--write-batch',type=int,default=128);p.add_argument('--read-batch',type=int,default=256)
    p.add_argument('--write-repeats',type=int,default=3);p.add_argument('--read-repeats',type=int,default=3)
    p.add_argument('--queries',type=int,default=48);p.add_argument('--cache-mib',type=int,default=8)
    p.add_argument('--seed',type=int,default=20261006);p.add_argument('--compression',choices=['none','lzf','gzip'],default='none')
    p.add_argument('--gpu',action='store_true');p.add_argument('--keep-files',action='store_true')
    p.add_argument('--overwrite',action='store_true',help='replace prior benchmark outputs in --out')
    args=p.parse_args()
    if min(args.rows,args.cols,args.channels,args.samples,args.write_batch,args.read_batch,args.write_repeats,args.read_repeats,args.queries,args.cache_mib)<1:
        p.error('all integer size/count options must be positive')
    n=args.rows*args.cols;c=args.channels;s=args.samples
    if args.read_batch>n:p.error('read-batch must not exceed trigger count')
    args.out.mkdir(parents=True,exist_ok=True)
    conflicts=[args.out/'results.json',args.out/'summary.csv']+[args.out/(x.name+'.h5') for x in layouts(c,s)]
    if not args.overwrite and any(x.exists() for x in conflicts):
        p.error('benchmark outputs already exist; choose a new --out or explicitly use --overwrite')
    settings=vars(args).copy();settings['out']=str(args.out.resolve())
    result={'experiment_id':'ultrasound_fixed_layout_microbenchmark_v1',
            'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'settings':settings,'environment':env(),
            'scope':'synthetic conventional uniform layout only','cache_regime':'OS warm/uncontrolled, bounded raw chunk cache, no cache drop',
            'not_measured':['cold-storage bandwidth','durable/fsync bandwidth','acquisition-device input','concurrent writer-reader',
                            'UI rendering','PA/FMC','GPU compute','double-buffer overlap'],
            'layouts':{}}
    rng=np.random.default_rng(args.seed)
    data=rng.integers(-32768,32768,size=(n,c,s),dtype=np.int16)
    status=np.full((n,c),3,dtype='u1');status[rng.random((n,c))<.05]=1
    result['synthetic_data']={'shape_TCS':[n,c,s],'dtype':'<i2','waveform_bytes':data.nbytes,
          'distribution':'uniform full-range int16; not representative of measured echo compressibility',
          'present_invalid_count':int(np.sum(status==1)),'all_payload_present':True}
    candidates=layouts(c,s);random.Random(args.seed).shuffle(candidates)
    result['execution_order']=[x.name for x in candidates]
    for lay in candidates:
        print('RUN',lay.name,flush=True)
        write_seconds=[];batch_seconds=[];neg=None;path=args.out/(lay.name+'.h5')
        for rep in range(args.write_repeats):
            store=Store(path,lay,c,s,'w',args.cache_mib*MIB,None if args.compression=='none' else args.compression)
            if rep==0:neg=negative_checks(store,data,status)
            t0=time.perf_counter()
            for a in range(0,n,args.write_batch):
                t1=time.perf_counter();store.append(data[a:a+args.write_batch],status[a:a+args.write_batch]);batch_seconds.append(time.perf_counter()-t1)
            store.close();write_seconds.append(time.perf_counter()-t0)
        store=Store(path,lay,c,s,'r',args.cache_mib*MIB)
        rec={'layout':asdict(lay),'chunk_bytes':lay.bt*lay.bc*lay.bs*2,
             'waveform_cache_budget_bytes':args.cache_mib*MIB,
             'raw_cache_bytes_per_waveform_dataset':args.cache_mib*MIB//(c if lay.order=='SPLIT' else 1),
             'file_bytes':path.stat().st_size,'write_seconds':write_seconds,
             'write_logical_MiB_s_median':float(data.nbytes/MIB/np.median(write_seconds)),
             'write_batch_latency':summarize(batch_seconds),'write_batch_raw_seconds':batch_seconds,
             'negative_tests':neg,'validation':verify(store,data,status,args.read_batch),
             'reads':run_reads(store,data,args),'gpu':run_gpu(store,args)}
        store.close();result['layouts'][lay.name]=rec
        if not args.keep_files:path.unlink()
        (args.out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        gc.collect()
    with (args.out/'summary.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['layout','workload','n','median_ms','p95_ms','logical_MiB_s'])
        for name,rec in result['layouts'].items():
            w.writerow([name,'write_total',args.write_repeats,np.median(rec['write_seconds'])*1000,'',rec['write_logical_MiB_s_median']])
            for kind,m in rec['reads'].items():w.writerow([name,kind,m['n'],m['median_ms'],m['p95_ms'],m['logical_MiB_s']])
    print('COMPLETE',args.out/'results.json',flush=True)

if __name__=='__main__':main()
