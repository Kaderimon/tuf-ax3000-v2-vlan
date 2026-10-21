# kocheck.py <System.map> <modules dir>: every undefined symbol of every .ko must be exported
# by the kernel (__ksymtab_ in System.map) or by another module.
import sys,os,subprocess,re
ex=set(l.split()[2][len('__ksymtab_'):] for l in open(sys.argv[1]) if ' __ksymtab_' in l)
kos=[os.path.join(d,f) for d,_,fs in os.walk(sys.argv[2]) for f in fs if f.endswith('.ko')]
und={}
for k in kos:
    out=subprocess.run(['readelf','-W','-s',k],capture_output=True,text=True).stdout
    for l in out.splitlines():
        c=l.split()
        if len(c)<8 or not c[0][:-1].isdigit(): continue
        if c[7].startswith('__ksymtab_') and c[6]!='UND': ex.add(c[7][len('__ksymtab_'):])
        elif c[6]=='UND' and c[4] in ('GLOBAL',): und.setdefault(k,set()).add(c[7])
bad={k:sorted(v-ex) for k,v in und.items() if v-ex}
print(f"{len(kos)} modules, {len(ex)} exported symbols; modules with unresolved: {len(bad)}")
for k,v in sorted(bad.items()): print(os.path.basename(k), v[:15], f"+{len(v)-15}" if len(v)>15 else "")
sys.exit(1 if bad else 0)
