import struct,sys
b=open(sys.argv[1],'rb').read()
magic,tot,offst,offstr,_,_,_,_,szstr,szst=struct.unpack('>10I',b[:40])
strs=b[offstr:offstr+szstr];p=offst;path=[]
nm=lambda o:strs[o:strs.index(b'\0',o)].decode()
pat=sys.argv[2].split(',')
while True:
    t,=struct.unpack('>I',b[p:p+4]);p+=4
    if t==1: e=b.index(b'\0',p);path.append(b[p:e].decode());p=(e+4)&~3
    elif t==2: path.pop()
    elif t==3:
        ln,no=struct.unpack('>II',b[p:p+8]);p+=8;v=b[p:p+ln];p=(p+ln+3)&~3
        full='/'.join(path)
        if not any(x in full for x in pat): continue
        n=nm(no)
        if ln and all(32<=c<127 or c==0 for c in v) and v[-1]==0: val=v.replace(b'\0',b' ').decode().strip()
        elif ln%4==0 and ln<=32: val=' '.join(hex(x) for x in struct.unpack('>%dI'%(ln//4),v))
        else: val=f'<{ln}b>'
        print(f'{full} {n}={val}')
    elif t==9: break
