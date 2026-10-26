"""Statement-level CFG for structured C; conservative treatment of switch/goto."""
from pycparser import c_ast, c_generator
GEN=c_generator.CGenerator()

def build_cfg(ast):
    nodes=[]; edges=[]; serial=0
    def new(label, kind='statement', line=0, function=''):
        nonlocal serial
        serial+=1; ident=f'cfg{serial}'
        nodes.append({'id':ident,'label':label[:95],'kind':kind,'line':line,'function':function})
        return ident
    def edge(a,b,label=''):
        if a and b: edges.append({'from':a,'to':b,'label':label})
    for fn in ast.ext:
        if not isinstance(fn,c_ast.FuncDef): continue
        fname=fn.decl.name
        entry=new(f'{fname}: ENTRY','entry',function=fname)
        end=new(f'{fname}: EXIT','exit',function=fname)
        def seq(items, nxt, break_to=None, continue_to=None):
            for item in reversed(items or []): nxt=stmt(item,nxt,break_to,continue_to)
            return nxt
        def stmt(s,nxt,break_to=None,continue_to=None):
            line=s.coord.line if s.coord else 0
            if isinstance(s,c_ast.Compound): return seq(s.block_items,nxt,break_to,continue_to)
            if isinstance(s,c_ast.If):
                q=new('if ('+GEN.visit(s.cond)+')','decision',line,fname)
                yes=stmt(s.iftrue,nxt,break_to,continue_to) if s.iftrue else nxt
                no=stmt(s.iffalse,nxt,break_to,continue_to) if s.iffalse else nxt
                edge(q,yes,'true');edge(q,no,'false');return q
            if isinstance(s,(c_ast.While,c_ast.For,c_ast.DoWhile)):
                cond=s.cond if hasattr(s,'cond') else None
                q=new(type(s).__name__+' ('+(GEN.visit(cond) if cond else 'true')+')','decision',line,fname)
                post=q
                if isinstance(s,c_ast.For) and s.next:
                    post=new(GEN.visit(s.next),'step',line,fname);edge(post,q)
                body=stmt(s.stmt,post,nxt,post)
                edge(q,body,'true');edge(q,nxt,'false')
                if isinstance(s,c_ast.DoWhile):
                    return body
                if isinstance(s,c_ast.For) and s.init:
                    return stmt(s.init,q,break_to,continue_to)
                return q
            if isinstance(s,c_ast.Break):
                n=new('break','jump',line,fname);edge(n,break_to or nxt);return n
            if isinstance(s,c_ast.Continue):
                n=new('continue','jump',line,fname);edge(n,continue_to or nxt);return n
            if isinstance(s,c_ast.Return):
                n=new(GEN.visit(s),'return',line,fname);edge(n,end);return n
            if isinstance(s,c_ast.Switch):
                n=new('switch ('+GEN.visit(s.cond)+')','decision',line,fname)
                cases=s.stmt.block_items if isinstance(s.stmt,c_ast.Compound) else []
                # Approximate dispatch edges; fallthrough represented by sequential cases.
                cur=nxt
                for case in reversed(cases):
                    if isinstance(case,(c_ast.Case,c_ast.Default)):
                        c=new(GEN.visit(case.expr) if isinstance(case,c_ast.Case) else 'default','case',line,fname)
                        first=seq(case.stmts,cur,nxt,continue_to)
                        edge(c,first);edge(n,c,'case');cur=c
                edge(n,nxt,'no match');return n
            if isinstance(s,(c_ast.Label,c_ast.Goto)):
                n=new(GEN.visit(s),'unsupported_jump',line,fname)
                # No invented edge for arbitrary goto; report limitation.
                if isinstance(s,c_ast.Label): edge(n,stmt(s.stmt,nxt,break_to,continue_to))
                return n
            n=new(GEN.visit(s),'statement',line,fname);edge(n,nxt);return n
        first=seq(fn.body.block_items,end)
        edge(entry,first)
    # Reachability and dominators for statement graph (one function at a time).
    ids={n['id'] for n in nodes}; succ={n:[] for n in ids};pred={n:[] for n in ids}
    for e in edges:
        succ[e['from']].append(e['to']);pred[e['to']].append(e['from'])
    reachable=set()
    for n in nodes:
        if n['kind']!='entry':continue
        stack=[n['id']]
        while stack:
            x=stack.pop()
            if x in reachable:continue
            reachable.add(x);stack.extend(succ[x])
    dominators={}
    for n in nodes:
        ident=n['id']
        if ident not in reachable:continue
        if n['kind']=='entry': dominators[ident]={ident}
        else: dominators[ident]={x['id'] for x in nodes if x['function']==n['function'] and x['id'] in reachable}
    changed=True
    while changed:
        changed=False
        for n in nodes:
            v=n['id']
            if v not in dominators or n['kind']=='entry':continue
            ps=[p for p in pred[v] if p in dominators]
            d=({v}|set.intersection(*(dominators[p] for p in ps))) if ps else {v}
            if d!=dominators[v]: dominators[v]=d;changed=True
    return {'nodes':nodes,'edges':edges,'reachable':sorted(reachable),
            'dominators':{k:sorted(v) for k,v in dominators.items()},
            'note':'Statement-level structured CFG. Switch fallthrough approximated; goto/labels not resolved. Dominators calculated on reachable nodes.'}
