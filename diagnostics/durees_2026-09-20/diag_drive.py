"""Pilote : N passes comparables SANS modifier le code. Pour chaque passe : instantané système, suite complète mesurée, PostgreSQL par phase, porte AP par étape,
puis recoupement avec le journal d'alimentation Windows (veilles chevauchant la fenêtre de la passe). Écrit un JSON par passe.
Usage : python diag_drive.py DOSSIER_SORTIE NOM_PASSE [NOM_PASSE ...]
"""
import datetime
import json
import os
import subprocess
import sys
import time

DIAG = os.path.dirname(os.path.abspath(__file__))
REG = r'C:\Users\HP\Links\verqia-docs\architecture_registry'
PS = ['powershell', '-NoProfile', '-Command']


def ps(cmd):
    out = subprocess.run(PS + ['[Console]::OutputEncoding=[Text.Encoding]::UTF8; ' + cmd], capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
    return (out or '').strip()


def snapshot():
    load = ps("(Get-CimInstance Win32_Processor).LoadPercentage")
    mem = ps("$o=Get-CimInstance Win32_OperatingSystem; [int]($o.FreePhysicalMemory/1024)")
    procs = ps("(Get-Process python* -ErrorAction SilentlyContinue | Measure-Object).Count")
    return {'cpu_load_pct': load, 'ram_libre_mo': mem, 'processus_python': procs}


def sleeps(start, end):
    """Veilles (Power-Troubleshooter id 1 : « Temps de veille » → « Temps de réveil ») chevauchant [start, end] en UTC ; le fuseau de la machine est UTC."""
    import re
    cmd = ("$e=Get-WinEvent -FilterHashtable @{LogName='System';ProviderName='Microsoft-Windows-Power-Troubleshooter';Id=1;StartTime=[datetime]'%s';EndTime=[datetime]'%s'} -ErrorAction SilentlyContinue;"
           "$e | ForEach-Object { ($_.Message -replace \"[\r\n]+\",' ') }") % (
        (start - datetime.timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S'), (end + datetime.timedelta(hours=6)).strftime('%Y-%m-%d %H:%M:%S'))
    total = 0.0
    found = []
    for line in ps(cmd).splitlines():
        line = line.replace('‎', '')
        stamps = re.findall(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)Z', line)
        if len(stamps) < 2:
            continue
        s0, w0 = (datetime.datetime.fromisoformat(x[:26]) for x in stamps[:2])
        lo, hi = max(s0, start), min(w0, end)
        if hi > lo:
            total += (hi - lo).total_seconds()
            found.append([s0.isoformat(), w0.isoformat()])
    return total, found


def run(script, out, cwd):
    t = time.perf_counter()
    p = subprocess.run([sys.executable, os.path.join(DIAG, script), out], cwd=cwd, capture_output=True, text=True, encoding='utf-8',
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    return {'wall': time.perf_counter() - t, 'returncode': p.returncode, 'stderr_tail': p.stderr[-300:]}


def main():
    folder, names = sys.argv[1], sys.argv[2:]
    os.makedirs(folder, exist_ok=True)
    for name in names:
        rec = {'pass': name, 'snapshot_before': snapshot()}
        start = datetime.datetime.utcnow()
        t0, w0 = time.perf_counter(), time.time()
        rec['suite'] = run('diag_suite.py', os.path.join(folder, name + '_suite.json'), REG)
        rec['postgres'] = run('diag_pg.py', os.path.join(folder, name + '_pg.json'), REG)
        rec['gate'] = run('diag_gate.py', os.path.join(folder, name + '_gate.json'), REG)
        end = datetime.datetime.utcnow()
        rec['wall'] = time.perf_counter() - t0
        rec['wall_clock'] = time.time() - w0
        rec['start_utc'], rec['end_utc'] = start.isoformat(), end.isoformat()
        rec['sleep_overlap_s'], rec['sleep_windows'] = sleeps(start, end)
        rec['snapshot_after'] = snapshot()
        with open(os.path.join(folder, name + '_pass.json'), 'w', encoding='utf-8') as f:
            json.dump(rec, f, ensure_ascii=False, indent=1)
        print(name, 'terminée : %.0f s (veille %.0f s)' % (rec['wall'], rec['sleep_overlap_s']), flush=True)


if __name__ == '__main__':
    main()
