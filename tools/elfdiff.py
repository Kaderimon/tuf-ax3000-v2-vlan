# elfdiff.py <stock.json> <new.json>: elfcheck problems present in the new rootfs but not in stock.
# Libraries with unresolved symbols are normal (resolved by the loading program); only executables
# and missing libraries count. Exit 1 if any.
import json,sys
s=json.load(open(sys.argv[1]));n=json.load(open(sys.argv[2]));bad=0
cnt=lambda d:sum(1 for v in d.values() if v['exe'] and (v['missing'] or v['unres']))
print(f"ELFs: stock {len(s)}, new {len(n)}; executables with problems: stock {cnt(s)}, new {cnt(n)}")
for p,v in sorted(n.items()):
    o=s.get(p,{'missing':[],'unres':[]})
    m=sorted(set(v['missing'])-set(o['missing']));u=sorted(set(v['unres'])-set(o['unres'])) if v['exe'] else []
    if m or u:
        bad+=1;print(p,'(not in stock)' if p not in s else '')
        if m: print('   missing:',m)
        if u: print('   unresolved:',u[:40],f'(+{len(u)-40})' if len(u)>40 else '')
sys.exit(1 if bad else 0)
