# SPDX-License-Identifier: CERN-OHL-S-2.0
# Minimal S-expression reader/writer for KiCad files.
import re
TOK=re.compile(r'\s*(?:(\()|(\))|("(?:\\.|[^"\\])*")|([^\s()"]+))')
def parse(s):
    stack=[[]];i=0
    while True:
        m=TOK.match(s,i)
        if not m or m.end()==i: break
        i=m.end()
        if m.group(1): stack.append([])
        elif m.group(2): x=stack.pop(); stack[-1].append(x)
        elif m.group(3): stack[-1].append(Q(m.group(3)[1:-1].replace('\\"','"').replace('\\\\','\\')))
        elif m.group(4): stack[-1].append(m.group(4))
    return stack[0]
class Q(str): pass
def dump(x,ind=0):
    if isinstance(x,list):
        if not x: return '()'
        simple=all(not isinstance(e,list) for e in x)
        if simple: return '('+' '.join(dump(e) for e in x)+')'
        out='('+dump(x[0])
        for e in x[1:]:
            out+='\n'+'\t'*(ind+1)+dump(e,ind+1) if isinstance(e,list) else ' '+dump(e)
        return out+'\n'+'\t'*ind+')'
    if isinstance(x,Q): return '"'+x.replace('\\','\\\\').replace('"','\\"')+'"'
    return str(x)
