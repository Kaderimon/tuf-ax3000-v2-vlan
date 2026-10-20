import struct,sys
b=open(sys.argv[1],'rb').read();want=sys.argv[2]
magic,tot,offst,offstr,_,_,_,_,szstr,szst=struct.unpack('>10I',b[:40])
strs=b[offstr:offstr+szstr];p=offst;path=[];props={}
nm=lambda o:strs[o:strs.index(b'\0',o)].decode()
while True:
    t,=struct.unpack('>I',b[p:p+4]);p+=4
    if t==1: e=b.index(b'\0',p);path.append(b[p:e].decode());p=(e+4)&~3
    elif t==2: path.pop()
    elif t==3:
        ln,no=struct.unpack('>II',b[p:p+8]);p+=8;v=b[p:p+ln];p=(p+ln+3)&~3
        if path[-1]==want: props[nm(no)]=v
    elif t==9: break
pos=struct.unpack('>I',props['data-position'])[0];sz=struct.unpack('>I',props['data-size'])[0]
sys.stdout.buffer.write(b[pos:pos+sz])
