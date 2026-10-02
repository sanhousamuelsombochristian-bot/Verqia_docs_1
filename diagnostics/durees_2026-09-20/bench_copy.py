"""Micro-mesure : 20 copies identiques de verqia-app (comme un test d'injection), avec le temps CPU de MsMpEng (Defender) avant/après."""
import json, os, shutil, subprocess, sys, tempfile, time
SRC = r'C:\Users\HP\Links\verqia-app'
def defender_cpu():
    out = subprocess.run(['powershell','-NoProfile','-Command',"(Get-Process MsMpEng -ErrorAction SilentlyContinue | Measure-Object CPU -Sum).Sum"],capture_output=True,text=True).stdout.strip()
    try: return float(out.replace(',', '.'))
    except ValueError: return None
def files(p): return sum(len(f) for _,_,f in os.walk(p))
runs=[]
for r in range(3):
    d0=defender_cpu(); c0=time.process_time(); t0=time.perf_counter(); times=[]
    for i in range(20):
        dst=tempfile.mkdtemp(prefix='verqia_bench_'); t=time.perf_counter()
        shutil.copytree(os.path.join(SRC,'verqia'), os.path.join(dst,'verqia'), ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(os.path.join(SRC,'application_runner'), os.path.join(dst,'application_runner'), ignore=shutil.ignore_patterns('__pycache__'))
        times.append(time.perf_counter()-t); shutil.rmtree(dst, ignore_errors=True)
    wall=time.perf_counter()-t0; d1=defender_cpu()
    runs.append({'wall':wall,'mean_copy_s':sum(times)/20,'min':min(times),'max':max(times),'python_cpu':time.process_time()-c0,'defender_cpu_delta':None if d0 is None or d1 is None else d1-d0})
n=files(os.path.join(SRC,'verqia'))+files(os.path.join(SRC,'application_runner'))
print(json.dumps({'fichiers_copies_par_test': n, 'runs': runs}))
