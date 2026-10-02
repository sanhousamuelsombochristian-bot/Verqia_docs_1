"""Charge fixe (calcul pur) répétée à intervalles : la variation mesure la machine, pas le code. Fréquence CPU échantillonnée pendant la charge."""
import json, subprocess, threading, time
def work():
    x = 0
    for i in range(6_000_000):
        x += i * i % 7
    return x
def clock():
    out = subprocess.run(['powershell','-NoProfile','-Command',"$p=Get-CimInstance Win32_Processor; \"$($p.CurrentClockSpeed)|$($p.MaxClockSpeed)|$($p.LoadPercentage)\""],capture_output=True,text=True).stdout.strip()
    return out
rows=[]
for k in range(8):
    box={}
    th=threading.Thread(target=lambda: box.update(c=clock())); 
    t=time.perf_counter(); c=time.process_time()
    th.start(); work(); th.join()
    rows.append({'essai':k+1,'wall_s':round(time.perf_counter()-t,2),'cpu_s':round(time.process_time()-c,2),'MHz|max|charge%':box.get('c')})
    time.sleep(15)
w=[r['wall_s'] for r in rows]
print(json.dumps({'runs':rows,'min':min(w),'max':max(w),'ecart_pct':round((max(w)-min(w))/(sum(w)/len(w))*100,1)}, ensure_ascii=False))
