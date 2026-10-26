"""Conservative educational C optimizer for straight-line integer code.
Unsupported control flow remains unchanged; never executes submitted code.
"""
import copy
import re
from collections import Counter
from pycparser import c_parser, c_ast, c_generator

PARSER = c_parser.CParser()
GEN = c_generator.CGenerator()
WEIGHTS = {'+': 1, '-': 1, '*': 3, '/': 5, '%': 5, '<<': 1, '>>': 1,
           '&': 1, '|': 1, '^': 1, '==': 1, '!=': 1, '<': 1, '>': 1,
           '<=': 1, '>=': 1, '&&': 1, '||': 1}
PURE_BINARY = set(WEIGHTS)

def ids(node):
    names = set()
    class V(c_ast.NodeVisitor):
        def visit_ID(self, n): names.add(n.name)
    if node is not None: V().visit(node)
    return names

def has_effect(node):
    if node is None: return False
    class V(c_ast.NodeVisitor):
        def __init__(self): self.effect = False
        def visit_FuncCall(self, n): self.effect = True
        def visit_Assignment(self, n): self.effect = True
        def visit_UnaryOp(self, n):
            if n.op in ('p++','p--','++','--'): self.effect = True
            self.generic_visit(n)
    v = V(); v.visit(node)
    return v.effect

def simple_expr(node):
    if isinstance(node, (c_ast.ID, c_ast.Constant)): return True
    if isinstance(node, c_ast.BinaryOp) and node.op in PURE_BINARY:
        return simple_expr(node.left) and simple_expr(node.right)
    return False

def numeric(n):
    if not isinstance(n, c_ast.Constant) or n.type not in ('int', 'unsigned int'): return None
    if re.search(r'[uUlL]$', n.value): return None
    value = n.value
    try: return int(value, 0) if value != '0' else 0
    except ValueError: return None

def folding(node, line, findings):
    if not isinstance(node, c_ast.BinaryOp): return node
    node.left = folding(node.left, line, findings)
    node.right = folding(node.right, line, findings)
    a, b = numeric(node.left), numeric(node.right)
    if a is None or b is None: return node
    try:
        # No integer-overflow assumptions; conservative 32-bit signed range.
        ops = {'+': lambda: a+b, '-': lambda: a-b, '*': lambda: a*b,
               '/': lambda: int(a/b), '%': lambda: a-int(a/b)*b}
        if node.op not in ops or (node.op in ('/','%') and b == 0): return node
        result = ops[node.op]()
        if not (-2**31 <= result < 2**31): return node
        findings.append({'line':line,'kind':'Constant folding','detail':f'{GEN.visit(node)} → {result}','applied':True})
        return c_ast.Constant('int',str(result))
    except (OverflowError, ZeroDivisionError): return node

def unsigned_vars(block):
    out = set()
    for s in block:
        if isinstance(s,c_ast.Decl) and isinstance(s.type,c_ast.TypeDecl):
            typ = s.type.type
            if isinstance(typ,c_ast.IdentifierType) and typ.names == ['unsigned','int']:
                out.add(s.name)
    return out

def strength(node, unsigned, line, findings):
    if not isinstance(node,c_ast.BinaryOp): return node
    node.left = strength(node.left,unsigned,line,findings)
    node.right = strength(node.right,unsigned,line,findings)
    if node.op != '*': return node
    for expr, const in ((node.left,node.right),(node.right,node.left)):
        k = numeric(const)
        if (isinstance(expr,c_ast.ID) and expr.name in unsigned and k is not None
            and k > 1 and (k & (k-1)) == 0):
            shift = k.bit_length()-1
            findings.append({'line':line,'kind':'Strength reduction',
                             'detail':f'{GEN.visit(node)} → {expr.name} << {shift}', 'applied':True})
            return c_ast.BinaryOp('<<',copy.deepcopy(expr),c_ast.Constant('int',str(shift)))
    return node

def expr_of(s):
    if isinstance(s,c_ast.Decl): return s.init
    if isinstance(s,c_ast.Assignment) and s.op == '=' and isinstance(s.lvalue,c_ast.ID): return s.rvalue
    return None

def target_of(s):
    if isinstance(s,c_ast.Decl): return s.name
    if isinstance(s,c_ast.Assignment) and s.op == '=' and isinstance(s.lvalue,c_ast.ID): return s.lvalue.name
    return None

def assign_expr(s,e):
    if isinstance(s,c_ast.Decl): s.init = e
    else: s.rvalue = e

def eligible(s):
    if isinstance(s,c_ast.Decl):
        return (isinstance(s.type,c_ast.TypeDecl) and
                isinstance(s.type.type,c_ast.IdentifierType) and
                s.type.type.names in (['int'],['unsigned','int']))
    if isinstance(s,c_ast.Assignment):
        return s.op == '=' and isinstance(s.lvalue,c_ast.ID)
    return isinstance(s,(c_ast.Return,c_ast.EmptyStatement))

def integer_type(stmt):
    if not isinstance(stmt, c_ast.Decl) or not isinstance(stmt.type, c_ast.TypeDecl):
        return None
    t = stmt.type.type
    if not isinstance(t, c_ast.IdentifierType): return None
    names = set(t.names)
    if names == {'int'}: return 'signed'
    if names == {'unsigned', 'int'}: return 'unsigned'
    return None

def optimize_block(block, findings, notices):
    stmts = block.block_items or []
    if not stmts: return
    # This pass is deliberately restricted to a complete, self-contained,
    # straight-line function body. Unsupported constructs are not rewritten.
    if not all(eligible(s) for s in stmts):
        notices.append('Skipped a block containing unsupported statements or control flow.')
        return
    if any((expr_of(s) is not None and not simple_expr(expr_of(s))) or
           (isinstance(s,c_ast.Return) and s.expr is not None and not simple_expr(s.expr))
           for s in stmts):
        notices.append('Skipped a block with function calls, pointers, or complex expressions.')
        return
    declarations = [s for s in stmts if isinstance(s,c_ast.Decl)]
    declared = [s.name for s in declarations]
    if len(declared) != len(set(declared)) or any(integer_type(s) is None for s in declarations):
        notices.append('Skipped a block with duplicate or unsupported declarations.')
        return
    declared_set = set(declared)
    if any(ids(expr_of(s))-declared_set for s in stmts if expr_of(s) is not None) or any(
        isinstance(s,c_ast.Return) and s.expr is not None and ids(s.expr)-declared_set for s in stmts):
        notices.append('Skipped a block using nonlocal or parameter variables.')
        return
    if any(isinstance(s,c_ast.Assignment) and s.lvalue.name not in declared_set for s in stmts):
        notices.append('Skipped a block with nonlocal assignments.')
        return
    # Reject reads of locals before their first initialization.
    initialized = set()
    for s in stmts:
        expr = s.expr if isinstance(s,c_ast.Return) else expr_of(s)
        if ids(expr)-initialized:
            notices.append('Skipped a block with potentially uninitialized reads.')
            return
        target = target_of(s)
        if target and expr is not None: initialized.add(target)
    types = {s.name: integer_type(s) for s in declarations}
    unsigned = {k for k,v in types.items() if v == 'unsigned'}
    # Signed arithmetic may overflow, so only fold literal expressions whose
    # result is representable as signed 32-bit. Unsigned strength reduction is
    # restricted to expressions whose result is used in an unsigned variable.
    for s in stmts:
        expr = expr_of(s)
        if expr is None: continue
        line = s.coord.line if s.coord else 0
        expr = folding(expr, line, findings)
        if target_of(s) in unsigned:
            expr = strength(expr, unsigned, line, findings)
        assign_expr(s, expr)
    # Available-expression table with dependency invalidation. Avoid reuse
    # across differing declared types; retain a previous destination only if
    # its value remains unchanged. Conservative for mixed signedness.
    seen = {}
    for s in stmts:
        name = target_of(s)
        expr = expr_of(s)
        line = s.coord.line if s.coord else 0
        candidate = None
        if isinstance(expr, c_ast.BinaryOp) and simple_expr(expr) and name:
            key = GEN.visit(expr)
            prior = seen.get(key)
            if prior and prior[0] != name and types[prior[0]] == types[name]:
                candidate = prior[0]
        if name:
            seen = {k:v for k,v in seen.items() if name not in v[1] and name != v[0]}
        if candidate:
            findings.append({'line':line,'kind':'Common subexpression elimination',
                             'detail':f'{GEN.visit(expr)} → reuse {candidate}', 'applied':True})
            assign_expr(s, c_ast.ID(candidate))
        elif name and isinstance(expr,c_ast.BinaryOp) and name not in ids(expr):
            seen[GEN.visit(expr)] = (name, ids(expr))
    # Backward liveness: remove dead stores and their pure expressions.
    # Preserve declarations if a later assignment needs the declared name.
    live = set()
    kept = []
    assignment_targets = {target_of(s) for s in stmts if isinstance(s,c_ast.Assignment)}
    for s in reversed(stmts):
        name, expr = target_of(s), expr_of(s)
        if isinstance(s,c_ast.Return):
            live |= ids(s.expr)
            kept.append(s)
            continue
        if name is None:
            kept.append(s)
            continue
        if name not in live and not has_effect(expr):
            if isinstance(s,c_ast.Decl) and name in assignment_targets:
                # Keep declaration, but remove its dead initializer.
                if s.init is not None:
                    findings.append({'line':s.coord.line if s.coord else 0,
                                     'kind':'Dead code elimination',
                                     'detail':f'Removed dead initializer of {name}', 'applied':True})
                    s.init = None
                kept.append(s)
            else:
                findings.append({'line':s.coord.line if s.coord else 0,
                                 'kind':'Dead code elimination',
                                 'detail':f'Removed unused {name} definition', 'applied':True})
            continue
        live.discard(name)
        live |= ids(expr)
        kept.append(s)
    block.block_items = list(reversed(kept))

def cost(node):
    count=Counter()
    class V(c_ast.NodeVisitor):
        def visit_BinaryOp(self,n):
            count[n.op]+=1
            self.generic_visit(n)
    V().visit(node)
    return sum(WEIGHTS.get(op,1)*num for op,num in count.items()),dict(count)

def dag(tree):
    nodes=[]; edges=[]; index=0
    class V(c_ast.NodeVisitor):
        def visit_BinaryOp(self,n):
            nonlocal index
            key=GEN.visit(n)
            index+=1; ident='n'+str(index)
            nodes.append({'id':ident,'label':n.op,'title':key,'group':'operation'})
            for child in (n.left,n.right):
                if isinstance(child,c_ast.BinaryOp): childid=self.visit_BinaryOp(child)
                else:
                    label=GEN.visit(child); childid='leaf_'+re.sub(r'\W','_',label)
                    if not any(z['id']==childid for z in nodes):
                        nodes.append({'id':childid,'label':label,'group':'operand'})
                edges.append({'from':childid,'to':ident})
            return ident
    V().visit(tree)
    return {'nodes':nodes[:100],'edges':edges[:150]}

def analyze(source):
    if len(source)>30000: return {'error':'Source exceeds 30,000 characters.'}
    try: original=PARSER.parse(source)
    except Exception as e: return {'error':f'Unable to parse C source: {e}. Remove #include/#define and use supported C syntax.'}
    before,operations_before=cost(original)
    transformed=copy.deepcopy(original)
    findings=[]; notices=[]
    global_decls = any(isinstance(ext, c_ast.Decl) for ext in transformed.ext)
    for ext in transformed.ext:
        if isinstance(ext,c_ast.FuncDef):
            params = ext.decl.type.args
            has_params = bool(params and any(not (isinstance(p,c_ast.Typename) and
                isinstance(p.type,c_ast.TypeDecl) and
                isinstance(p.type.type,c_ast.IdentifierType) and p.type.type.names==['void'])
                for p in params.params))
            if global_decls or has_params:
                notices.append('Skipped function with globals or parameters.')
            else:
                optimize_block(ext.body,findings,notices)
    from branch_pass import optimize_branches
    from controlflow import build_cfg
    findings.extend(optimize_branches(transformed))
    from advanced_loops import optimize_advanced_loops
    findings.extend(optimize_advanced_loops(transformed))
    after,operations_after=cost(transformed)
    return {'original':source,'optimized':GEN.visit(transformed),
            'findings':sorted(findings,key=lambda f:f['line']),
            'before':before,'after':after,'reduction':round((before-after)*100/before,2) if before else 0,
            'operations_before':operations_before,'operations_after':operations_after,
            'summary':dict(Counter(f['kind'] for f in findings)),
            'graph':dag(original),'cfg':build_cfg(original),'optimized_cfg':build_cfg(transformed),'notices':list(dict.fromkeys(notices)),
            'cost_model':{'weights':WEIGHTS,'unit':'illustrative weighted static operation score','runtime_frequency_model':'not available'},
            'note':'Static weighted-operation proxy, NOT measured energy. Counts syntactic operations, not dynamic loop iterations. Advanced loop transformations only apply to a tightly restricted unsigned-integer subset; hardware measurements are separate.'}
