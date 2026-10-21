# split an outer .pkgtb FIT into its images (bootfs, rootfs) and verify each sha256: pkgsplit.py <pkgtb> <outdir>
import struct,sys,hashlib,os
b=open(sys.argv[1],'rb').read();out=sys.argv[2]
magic,tot,offst,offstr,_,_,_,_,szstr,szst=struct.unpack('>10I',b[:40])
assert magic==0xd00dfeed
strs=b[offstr:offstr+szstr];p=offst;path=[];nodes={}
nm=lambda o:strs[o:strs.index(b'\0',o)].decode()
while True:
    t,=struct.unpack('>I',b[p:p+4]);p+=4
    if t==1: e=b.index(b'\0',p);path.append(b[p:e].decode());p=(e+4)&~3
    elif t==2: path.pop()
    elif t==3:
        ln,no=struct.unpack('>II',b[p:p+8]);p+=8;v=b[p:p+ln];p=(p+ln+3)&~3
        nodes.setdefault('/'.join(path),{})[nm(no)]=v
    elif t==9: break
u32=lambda v:struct.unpack('>I',v)[0]
base=(tot+3)&~3;bad=0
for k,pr in nodes.items():
    if not k.startswith('/images/') or k.count('/')!=2 or 'data-size' not in pr: continue
    sz=u32(pr['data-size'])
    off=u32(pr['data-position']) if 'data-position' in pr else base+u32(pr['data-offset'])
    d=b[off:off+sz];ok=hashlib.sha256(d).digest()==nodes[k+'/hash-1']['value'];bad+=not ok
    name=k.split('/')[-1];open(os.path.join(out,name),'wb').write(d)
    print(f"{name}: {sz} bytes, sha256 {'OK' if ok else 'MISMATCH'} ({pr['description'].rstrip(b'|').rstrip(bytes(1)).decode()})")
sys.exit(1 if bad else 0)
