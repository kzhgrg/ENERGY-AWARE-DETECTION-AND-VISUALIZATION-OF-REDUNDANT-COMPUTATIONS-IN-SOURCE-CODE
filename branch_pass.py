"""Conservative branch simplification; never evaluates expressions with side effects."""
import copy
from pycparser import c_ast, c_generator
from analyzer import numeric, folding, has_effect
GEN=c_generator.CGenerator()

def truth(node):
    if isinstance(node,c_ast.Constant):
        v=numeric(node)
        return None if v is None else bool(v)
    if isinstance(node,c_ast.UnaryOp) and node.op=='!':
        v=truth(node.expr)
        return None if v is None else not v
    if isinstance(node,c_ast.BinaryOp):
        a=numeric(node.left);b=numeric(node.right)
        if a is not None and b is not None:
            ops={'==':a==b,'!=':a!=b,'<':a<b,'>':a>b,'<=':a<=b,'>=':a>=b}
            return ops.get(node.op)
        if node.op=='&&':
            x,y=truth(node.left),truth(node.right)
            if x is not None and y is not None:return x and y
        if node.op=='||':
            x,y=truth(node.left),truth(node.right)
            if x is not None and y is not None:return x or y
    return None

def optimize_branches(tree):
    findings=[]
    def safe_simple_loop_body(body):
        # Recursively simplify literal arithmetic inside loops. No speculative
        # loop-invariant hoisting or unrolling (requires alias/overflow proofs).
        if isinstance(body,c_ast.Compound):
            for stmt in body.block_items or []:
                if isinstance(stmt,c_ast.Decl) and stmt.init is not None:
                    stmt.init=folding(stmt.init,stmt.coord.line if stmt.coord else 0,findings)
                elif isinstance(stmt,c_ast.Assignment) and stmt.op=='=' and isinstance(stmt.lvalue,c_ast.ID):
                    stmt.rvalue=folding(stmt.rvalue,stmt.coord.line if stmt.coord else 0,findings)
        return body
    def walk(node):
        if node is None:return node
        if isinstance(node,c_ast.Compound):
            node.block_items=[walk(s) for s in (node.block_items or [])]
            return node
        if isinstance(node,c_ast.If):
            if not has_effect(node.cond):
                v=truth(node.cond)
                if v is not None:
                    findings.append({'line':node.coord.line if node.coord else 0,'kind':'Constant branch elimination',
                                     'detail':f'Condition always {v}; unreachable branch removed','applied':True})
                    return walk(node.iftrue if v else (node.iffalse or c_ast.EmptyStatement()))
            node.iftrue=walk(node.iftrue)
            if node.iffalse:node.iffalse=walk(node.iffalse)
            return node
        if isinstance(node,c_ast.While):
            if not has_effect(node.cond) and truth(node.cond) is False:
                findings.append({'line':node.coord.line if node.coord else 0,'kind':'Zero-iteration loop elimination',
                                 'detail':'while condition is always false','applied':True})
                return c_ast.EmptyStatement()
            node.stmt=walk(safe_simple_loop_body(node.stmt));return node
        if isinstance(node,c_ast.For):
            # For loops with provably false initial condition, the initializer
            # must still execute; only eliminate if there is no initializer.
            if node.init is None and node.cond is not None and not has_effect(node.cond) and truth(node.cond) is False:
                findings.append({'line':node.coord.line if node.coord else 0,'kind':'Zero-iteration for elimination',
                                 'detail':'for condition is always false and has no initializer','applied':True})
                return c_ast.EmptyStatement()
            node.stmt=walk(safe_simple_loop_body(node.stmt));return node
        if isinstance(node,c_ast.DoWhile):
            node.stmt=walk(safe_simple_loop_body(node.stmt));return node
        if isinstance(node,c_ast.Switch):
            return node  # do not rewrite switch/case/fallthrough
        return node
    for fn in tree.ext:
        if isinstance(fn,c_ast.FuncDef):walk(fn.body)
    return findings
