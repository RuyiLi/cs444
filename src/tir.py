from __future__ import annotations
from functools import reduce
from typing import List, Dict, TypeVar

T = TypeVar("T")

class IRNode:
    label: str
    children: List[IRNode]

    def __init__(self, children = []):
        self.children = children

    def visit_children(self, visitor):
        return self

    def aggregate_children(self, visitor):
        return reduce(lambda a, c: visitor.bind(a, visitor.visit(self, c)),
            self.children, visitor.unit())

class IRStmt(IRNode):
    def __str__(self) -> str:
        return f"EMPTY"

class IRExpr(IRNode):
    is_constant: bool

    def __init__(self, children = [], is_constant = False):
        super().__init__(children)
        self.is_constant = is_constant


class IRConst(IRExpr):
    value: int

    def __init__(self, value: int):
        super().__init__([], True)
        self.value = value

    def __str__(self):
        return f"CONST({self.value})"


class IRTemp(IRExpr):
    name: str

    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def __str__(self):
        return f"TEMP({self.name})"


class IRBinExpr(IRExpr):
    op_type: str
    left: IRExpr
    right: IRExpr

    def __init__(self, op_type: str, left: IRExpr, right: IRExpr):
        super().__init__([left, right])
        self.op_type = op_type
        self.left = left
        self.right = right
        self.is_constant = left.is_constant and right.is_constant

    def __str__(self):
        return f"({self.left} {self.op_type} {self.right})"

    def visit_children(self, visitor):
        left_child = visitor.visit(self, self.left)
        right_child = visitor.visit(self, self.right)

        if left_child != self.left or right_child != self.right:
            return IRBinExpr(self.op_type, left_child, right_child)

        return self


class IRMem(IRExpr):
    address: IRExpr

    def __init__(self, address: IRExpr):
        super().__init__([address])
        self.address = address

    def __str__(self):
        return f"MEM({self.address})"

    def visit_children(self, visitor):
        child_expr = visitor.visitor(self, self.address)
        return IRMem(child_expr) if child_expr != self.address else self


class IRCall(IRExpr):
    target: IRExpr
    args: List[IRExpr]

    def __init__(self, target: IRExpr, args: List[IRExpr] = []):
        super().__init__([target] + args)
        self.target = target
        self.args = args

    def __str__(self):
        return f"CALL(target={self.target}, args=[{','.join(arg.__str__() for arg in self.args)}])"

    def visit_children(self, visitor):
        target_expr = visitor.visit(self, self.target)
        arg_exprs = [visitor.visit(self, arg) for arg in self.args]

        if target_expr != self.target or any(arg != arg_exprs[i] for i, arg in enumerate(self.args)):
            return IRCall(target_expr, arg_exprs)

        return self


class IRName(IRExpr):
    name: str

    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def __str__(self):
        return f"NAME({self.name})"


class IRESeq(IRExpr):
    stmt: IRStmt
    expr: IRExpr

    def __init__(self, stmt: IRStmt, expr: IRExpr):
        super().__init__([stmt, expr])
        self.stmt = stmt
        self.expr = expr

    def __str__(self):
        return f"ESEQ({self.stmt}, {self.expr})"

    def visit_children(self, visitor):
        child_stmt = visitor.visit(self, self.stmt)
        child_expr = visitor.visit(self, self.expr)

        if child_stmt != self.stmt or child_expr != self.expr:
            return IRESeq(child_stmt, child_expr)

        return self


class IRMove(IRStmt):
    target: IRExpr
    source: IRExpr

    def __init__(self, target: IRExpr, source: IRExpr):
        super().__init__([target, source])
        self.target = target
        self.source = source

    def __str__(self):
        return f"MOVE(target={self.target}, source={self.source})"

    def visit_children(self, visitor):
        child_target = visitor.visit(self, self.target)
        child_source = visitor.visit(self, self.source)

        if child_target != self.target or child_source != self.target:
            return IRMove(child_target, child_source)

        return self


class IRExp(IRStmt):
    expr: IRExpr

    def __init__(self, expr: IRExpr):
        super().__init__([expr])
        self.expr = expr

    def __str__(self):
        return f"EXP({self.expr})"

    def visit_children(self, visitor):
        child_expr = visitor.visit(self, self.expr)
        return IRExp(child_expr) if child_expr != self.expr else self


class IRSeq(IRStmt):
    stmts: List[IRStmt]
    replace_parent: bool

    def __init__(self, stmts: List[IRStmt], replace_parent = False):
        self.stmts = stmts
        self.replace_parent = replace_parent

        self.simplify_stmts()
        super().__init__(self.stmts)

    def __str__(self):
        return f"SEQ({', '.join(stmt.__str__() for stmt in self.stmts)})"

    def visit_children(self, visitor):
        child_stmts = [visitor.visit(self, child) for child in self.stmts]

        if any(stmt != child_stmts[i] for i, stmt in enumerate(self.stmts)):
            return IRSeq(child_stmts)

        return self

    def simplify_stmts(self):
        stmts = []

        for s in self.stmts:
            if s.__str__() == "EMPTY":
                continue

            if isinstance(s, IRSeq):
                s.simplify_stmts()
                stmts += s.stmts
            else:
                stmts.append(s)

        self.stmts = stmts


class IRJump(IRStmt):
    target: IRExpr

    def __init__(self, target: IRExpr):
        super().__init__([target])
        self.target = target

    def __str__(self):
        return f"JUMP({self.target})"

    def visit_children(self, visitor):
        child_target = visitor.visit(self, self.target)
        return IRJump(child_target) if child_target != self.target else self


class IRCJump(IRStmt):
    cond: IRExpr
    true_label: IRName
    false_label: IRName | None

    def __init__(self, cond: IRExpr, true_label: IRName, false_label = None):
        super().__init__([cond])
        self.cond = cond
        self.true_label = true_label
        self.false_label = false_label

    def __str__(self):
        return f"CJUMP(cond={self.cond}, true={self.true_label}, false={self.false_label})"

    def visit_children(self, visitor):
        child_cond = visitor.visit(self.cond)
        return IRCJump(child_cond, self.true_label, self.false_label) if child_cond != self.cond else self


class IRLabel(IRStmt):
    name: str

    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def __str__(self):
        return f"LABEL({self.name})"


class IRReturn(IRStmt):
    ret: IRExpr | None

    def __init__(self, ret: IRExpr | None):
        super().__init__([] if ret is None else [ret])
        self.ret = ret

    def __str__(self):
        return f"RETURN({self.ret})"

    def visit_children(self, visitor):
        child_ret = visitor.visit(self, self.ret)
        return IRReturn(child_ret) if child_ret != self.ret else self


class IRFuncDecl(IRNode):
    name: str
    body: IRStmt
    params: List[str]

    def __init__(self, name: str, body: IRStmt, params: List[str]):
        super().__init__([body])
        self.name = name
        self.body = body
        self.params = params

    def __str__(self):
        return f"FuncDecl({self.name}, {self.body})"

    def visit_children(self, visitor):
        child_body = visitor.visit(self, self.body)
        return IRFuncDecl(self.name, child_body, self.params) if child_body != self.body else self


class IRCompUnit(IRNode):
    name: str
    functions: Dict[str, IRFuncDecl]

    def __init__(self, name: str, functions: Dict[str, IRFuncDecl] = {}):
        super().__init__(functions.values())
        self.name = name
        self.functions = functions

    def __str__(self):
        return "COMPUNIT"

    def visit_children(self, visitor):
        child_funcs = [visitor.visit(self, func) for _, func in self.functions]

        if any(func != child_funcs[i] for i, func in enumerate(self.functions)):
            return IRCompUnit(self.name, child_funcs)

        return self
