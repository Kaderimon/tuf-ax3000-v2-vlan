# minimal FDT/FIT walker: prints node paths and short string props, and image data offsets
import struct,sys
b=open(sys.argv[1],'rb').read()
magic,tot,offst,offstr,_,_,_,_,szstr,szst=struct.unpack('>10I',b[:40])
assert magic==0xd00dfeed
strs=b[offstr:offstr+szstr]
p=offst;path=[]
def name(o): return strs[o:strs.index(b'\0',o)].decode()
while True:
    tok,=struct.unpack('>I',b[p:p+4]);p+=4
    if tok==1:
        e=b.index(b'\0',p);path.append(b[p:e].decode());p=(e+4)&~3
    elif tok==2: path.pop()
    elif tok==3:
        ln,no=struct.unpack('>II',b[p:p+8]);p+=8;v=b[p:p+ln];p=(p+ln+3)&~3
        n=name(no)
        if n in('data-offset','data-size','data-position'):
            print('/'.join(path),n,struct.unpack('>I',v)[0])
        elif ln<200 and all(32<=c<127 or c==0 for c in v):
            print('/'.join(path),n,v.replace(b'\0',b'|').decode())
        else: print('/'.join(path),n,f'<{ln} bytes>')
    elif tok==4: continue
    elif tok==9: break
print('header totalsize',tot)
