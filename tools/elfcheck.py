# elfcheck.py <rootfs> > report.json: for every ELF, check that its NEEDED libs are found (RPATH,
# /lib, /usr/lib) and its strong undefined dynamic symbols resolve within its load scope
import os,sys,subprocess,re,json
R=sys.argv[1]; DIRS=['/lib','/usr/lib']
def real(p):  # resolve symlinks inside rootfs
    for _ in range(40):
        f=R+p
        if not os.path.islink(f): return p if os.path.isfile(f) else None
        t=os.readlink(f); p=os.path.normpath(t if t.startswith('/') else os.path.join(os.path.dirname(p),t))
    return None
elfs={}
for d,_,fs in os.walk(R):
    for n in fs:
        f=os.path.join(d,n)
        if os.path.islink(f) or not os.path.isfile(f): continue
        with open(f,'rb') as h:
            if h.read(4)!=b'\x7fELF': continue
        elfs['/'+os.path.relpath(f,R)]=None
info={}
def load(p):
    if p in info: return info[p]
    out=subprocess.run(['readelf','-W','-d','--dyn-syms',R+p],capture_output=True,text=True).stdout
    need=re.findall(r'\(NEEDED\).*\[(.+?)\]',out)
    rp=[x for m in re.findall(r'\((?:RPATH|RUNPATH)\).*\[(.+?)\]',out) for x in m.split(':')]
    und=set();dfn=set()
    for l in out.splitlines():
        c=l.split()
        if len(c)<8 or not c[0].endswith(':') or not c[0][:-1].isdigit(): continue
        typ,bind,ndx,name=c[3],c[4],c[6],c[7].split('@')[0]
        if not name: continue
        if ndx=='UND':
            if bind=='GLOBAL': und.add(name)
        elif bind in('GLOBAL','WEAK','UNIQUE'): dfn.add(name)
    info[p]=dict(need=need,rp=rp,und=und,dfn=dfn,dyn='(NEEDED)' in out or 'DYNAMIC' in out,
                 interp='Requesting program interpreter' in subprocess.run(['readelf','-l',R+p],capture_output=True,text=True).stdout)
    return info[p]
def find(lib,rp):
    for d in rp+DIRS:
        q=real(os.path.join(d,lib))
        if q: return q
def scope(p):  # breadth-first load order, like ld.so
    order=[p];missing=[];i=0
    while i<len(order):
        e=load(order[i]);i+=1
        for lib in e['need']:
            q=find(lib,e['rp'])
            if q is None: missing.append(f"{lib} (needed by {order[i-1]})")
            elif q not in order: order.append(q)
    return order,missing
res={}
for p in sorted(elfs):
    if p.endswith('.ko'): continue
    e=load(p)
    if not e['need'] and not e['und']: continue
    order,missing=scope(p)
    defined=set().union(*(load(q)['dfn'] for q in order))
    unres=sorted(set().union(*(load(q)['und'] for q in order))-defined)
    res[p]=dict(exe=e['interp'],missing=sorted(set(missing)),unres=unres)
json.dump(res,sys.stdout,indent=0)
