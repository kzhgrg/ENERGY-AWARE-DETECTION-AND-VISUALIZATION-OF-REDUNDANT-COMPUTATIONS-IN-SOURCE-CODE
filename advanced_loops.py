"""Conservative loop transformations for an explicitly restricted subset of C.

No speculative side effects, pointer aliasing, break/continue, or arbitrary loops.
"""
import copy
from pycparser import c_ast
from analyzer import ids, numeric, has_effect, GEN


def _u32_decl(n):
    return (isinstance(n,c_ast.Decl) and isinstance(n.type,c_ast.TypeDecl)
            and isinstance(n.type.type,c_ast.IdentifierType)
            and set(n.type.type.names)=={'unsigned','int'})

def _decl(name, init):
    return c_ast.Decl(name=name, quals=[], align=[], storage=[], funcspec=[],
        type=c_ast.TypeDecl(declname=name, quals=[], align=None,
            type=c_ast.IdentifierType(['unsigned','int'])), init=init, bitsize=None)

def _const(x): return c_ast.Constant('int',str(x))
def _id(x): return c_ast.ID(x)
def _assign(name, op, rhs): return c_ast.Assignment(op,_id(name),rhs)

def _canonical(loop):
    if not isinstance(loop,c_ast.For) or not isinstance(loop.init,c_ast.DeclList) or len(loop.init.decls)!=1:return None
    d=loop.init.decls[0]
    if not _u32_decl(d) or numeric(d.init)!=0:return None
    cond=loop.cond
    if not isinstance(cond,c_ast.BinaryOp) or cond.op!='<' or not isinstance(cond.left,c_ast.ID) or cond.left.name!=d.name:return None
    bound=numeric(cond.right)
    if bound is None or bound<0 or bound>10000:return None
    step=loop.next
    if not isinstance(step,c_ast.UnaryOp) or step.op not in ('p++','++') or not isinstance(step.expr,c_ast.ID) or step.expr.name!=d.name:return None
    return d.name,bound

def _safe_body(body):
    if not isinstance(body,c_ast.Compound):return False
    for s in body.block_items or []:
        if not isinstance(s,c_ast.Assignment) or s.op not in ('=','+=') or not isinstance(s.lvalue,c_ast.ID) or has_effect(s.rvalue):return False
        if not _pure_arith(s.rvalue):return False
    return True

def _pure_arith(n):
    if isinstance(n,(c_ast.ID,c_ast.Constant)):return True
    return isinstance(n,c_ast.BinaryOp) and n.op in ('+','-','*','&','|','^') and _pure_arith(n.left) and _pure_arith(n.right)

def _replace(n, pred, new):
    if pred(n):return copy.deepcopy(new)
    if isinstance(n,c_ast.BinaryOp):
        n.left=_replace(n.left,pred,new);n.right=_replace(n.right,pred,new)
    return n

def optimize_advanced_loops(tree):
    findings=[]
    for fn in tree.ext:
        if not isinstance(fn,c_ast.FuncDef):continue
        # Require no globals and no function parameters. Nested scopes/shadowing
        # are rejected; only direct unsigned declarations and canonical for loops.
        if any(isinstance(e,c_ast.Decl) for e in tree.ext):continue
        args=fn.decl.type.args
        if args and any(not isinstance(p,c_ast.Typename) for p in args.params):continue
        block=fn.body
        items=block.block_items or []
        if any(isinstance(s,(c_ast.If,c_ast.While,c_ast.DoWhile,c_ast.Switch,c_ast.Goto,c_ast.Label)) for s in items):continue
        outer={s.name for s in items if _u32_decl(s)}
        allnames=set(outer)
        for s in items:
            if isinstance(s,c_ast.For) and isinstance(s.init,c_ast.DeclList):
                allnames.update(d.name for d in s.init.decls)
        counter=0
        output=[]
        for s in items:
            canon=_canonical(s)
            if not canon or not _safe_body(s.stmt):output.append(s);continue
            iv,bound=canon
            body=s.stmt.block_items or []
            writes=[t.lvalue.name for t in body]
            if iv in writes or any(w not in outer for w in writes) or len(set(writes))!=len(writes):
                output.append(s);continue
            # All values referenced must be unsigned locals, induction var, or literals.
            if any(ids(t.rvalue)-outer-{iv} for t in body):output.append(s);continue
            # Avoid shadowing, calls, or control transfers in the entire function.
            if any(isinstance(t,c_ast.For) and t is not s for t in body):output.append(s);continue
            line=s.coord.line if s.coord else 0
            # Induction variable strength reduction: i*k -> rolling unsigned temp.
            # Only one eligible occurrence in a += expression, k=2..16.
            iv_candidates=[]
            for t in body:
                def scan(n):
                    if isinstance(n,c_ast.BinaryOp):
                        if n.op=='*' and isinstance(n.left,c_ast.ID) and n.left.name==iv and numeric(n.right) in range(2,17):
                            iv_candidates.append((t,n,numeric(n.right)))
                        scan(n.left);scan(n.right)
                scan(t.rvalue)
            if len(iv_candidates)==1 and bound>=2:
                t,expr,k=iv_candidates[0]
                # The target is an unsigned accumulator, and not the loop counter.
                if t.op=='+=' and t.lvalue.name in outer and k*bound < 2**32:
                    counter+=1;tmp=f'__cf_induction_{counter}'
                    while tmp in allnames:counter+=1;tmp=f'__cf_induction_{counter}'
                    allnames.add(tmp)
                    output.append(_decl(tmp,_const(0)))
                    t.rvalue=_replace(t.rvalue,lambda n:n is expr,_id(tmp))
                    body.append(_assign(tmp,'+=',_const(k)))
                    findings.append({'line':line,'kind':'Induction-variable optimization','detail':f'Replaced {iv} * {k} with incremental {tmp}','applied':True})
                    output.append(s);continue
            # LICM: move an unsigned multiplication of two unmodified outer
            # variables from a loop expression into a preheader temporary.
            candidates=[]
            for t in body:
                def scan(n):
                    if isinstance(n,c_ast.BinaryOp):
                        if (n.op=='*' and isinstance(n.left,c_ast.ID) and isinstance(n.right,c_ast.ID)
                            and n.left.name in outer and n.right.name in outer
                            and n.left.name not in writes and n.right.name not in writes):candidates.append((t,n))
                        scan(n.left);scan(n.right)
                scan(t.rvalue)
            if len(candidates)==1 and bound>0:
                t,expr=candidates[0]
                counter+=1;tmp=f'__cf_invariant_{counter}'
                while tmp in allnames:counter+=1;tmp=f'__cf_invariant_{counter}'
                allnames.add(tmp)
                output.append(_decl(tmp,copy.deepcopy(expr)))
                t.rvalue=_replace(t.rvalue,lambda n:n is expr,_id(tmp))
                findings.append({'line':line,'kind':'Loop-invariant code motion','detail':f'Hoisted {GEN.visit(expr)} into {tmp}','applied':True})
                output.append(s);continue
            # Full unrolling for small fixed-trip loops, preserving the induction
            # variable's value at each iteration. Loop variable is scoped inside
            # the replacement compound just as in for(int i=...).
            if 1<=bound<=8:
                expanded=[copy.deepcopy(s.init.decls[0])]
                for _ in range(bound):
                    expanded.extend(copy.deepcopy(body))
                    expanded.append(copy.deepcopy(s.next))
                output.append(c_ast.Compound(expanded))
                findings.append({'line':line,'kind':'Loop unrolling','detail':f'Unrolled fixed-trip loop ({bound} iterations)','applied':True})
                continue
            output.append(s)
        block.block_items=output
    return findings
