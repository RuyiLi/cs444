from enum import Enum
from typing import List, Dict

class IRNode:
    label: str

    def visit_children(self, visitor):
        return self

class IRStmt(IRNode):
    pass

class IRExpr(IRNode):
    is_constant: bool


class IRConst(IRExpr):
    value: int

    def __init__(self, value: int):
        self.value = value
        self.is_constant = True

    def __repr__(self):
        return f"CONST({self.value})"


class IRTemp(IRExpr):
    name: str

    def __init__(self, name: str):
        self.name = name


class IRBinExpr(IRExpr):
    op_type: str
    left: IRExpr
    right: IRExpr

    def __init__(self, op_type: str, left: IRExpr, right: IRExpr):
        self.op_type = op_type
        self.left = left
        self.right = right
        self.is_constant = left.is_constant and right.is_constant

    def __repr__(self):
        return self.op_type

    def visit_children(self, visitor):
        left_child = visitor.visit(self, self.left)
        right_child = visitor.visit(self, self.right)

        if left_child != self.left or right_child != self.right:
            return IRBinExpr(self.op_type, left_child, right_child)

        return self


class IRMem(IRExpr):
    address: IRExpr

    def __init__(self, address: IRExpr):
        self.address = address

    def __repr__(self):
        return "MEM"

    def visit_children(self, visitor):
        child_expr = visitor.visitor(self, self.address)
        return IRMem(child_expr) if child_expr != self.address else self


class IRCall(IRExpr):
    target: IRExpr
    args: List[IRExpr]

    def __init__(self, target: IRExpr, args: List[IRExpr] = []):
        self.target = target
        self.args = args

    def __repr__(self):
        return "CALL"

    def visit_children(self, visitor):
        target_expr = visitor.visit(self, self.target)
        arg_exprs = [visitor.visit(self, arg) for arg in self.args]

        if target_expr != self.target or any(arg != arg_exprs[i] for i, arg in enumerate(self.args)):
            return IRCall(target_expr, arg_exprs)

        return self


class IRName(IRExpr):
    name: str

    def __init__(self, name: str):
        self.name = name

    def __repr__(self):
        return f"NAME({self.name})"


class IRESeq(IRExpr):
    stmt: IRStmt
    expr: IRExpr

    def __init__(self, stmt: IRStmt, expr: IRExpr):
        self.stmt = stmt
        self.expr = expr

    def __repr__(self):
        return "ESEQ"

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
        self.target = target
        self.source = source

    def __repr__(self):
        return "MOVE"

    def visit_children(self, visitor):
        child_target = visitor.visit(self, self.target)
        child_source = visitor.visit(self, self.source)

        if child_target != self.target or child_source != self.target:
            return IRMove(child_target, child_source)

        return self


class IRExp(IRStmt):
    expr: IRExpr

    def __init__(self, expr: IRExpr):
        self.expr = expr

    def __repr__(self):
        return "EXP"

    def visit_children(self, visitor):
        child_expr = visitor.visit(self, self.expr)
        return IRExp(child_expr) if child_expr != self.expr else self


class IRSeq(IRStmt):
    stmts: List[IRStmt]
    replace_parent: bool

    def __init__(self, stmts: List[IRStmt], replace_parent = False):
        self.stmts = stmts
        self.replace_parent = replace_parent

    def visit_children(self, visitor):
        child_stmts = [visitor.visit(self, child) for child in self.stmts]

        if any(stmt != child_stmts[i] for i, stmt in enumerate(self.stmts)):
            return IRSeq(child_stmts)

        return self


class IRJump(IRStmt):
    target: IRExpr

    def __init__(self, target: IRExpr):
        self.target = target

    def __repr__(self):
        return "JUMP"

    def visit_children(self, visitor):
        child_target = visitor.visit(self, self.target)
        return IRJump(child_target) if child_target != self.target else self


class IRCJump(IRStmt):
    cond: IRExpr
    true_label: str
    false_label: str | None

    def __init__(self, cond: IRExpr, true_label: str, false_label = None):
        self.cond = cond
        self.true_label = true_label
        self.false_label = false_label

    def visit_children(self, visitor):
        child_cond = visitor.visit(self.cond)
        return IRCJump(child_cond, self.true_label, self.false_label) if child_cond != self.cond else self


class IRLabel(IRStmt):
    name: str

    def __init__(self, name: str):
        self.name = name

    def __repr__(self):
        return f"LABEL({self.name})"


class IRReturn(IRStmt):
    ret: IRExpr | None

    def __init__(self, ret: IRExpr | None):
        self.ret = ret

    def __repr__(self):
        return "RETURN"

    def visit_children(self, visitor):
        child_ret = visitor.visit(self, self.ret)
        return IRReturn(child_ret) if child_ret != self.ret else self


class IRFuncDecl(IRNode):
    name: str
    body: IRStmt
    num_params: int

    def __init__(self, name: str, body: IRStmt, num_params: int):
        self.name = name
        self.body = body
        self.num_params = num_params

    def visit_children(self, visitor):
        child_body = visitor.visit(self, self.body)
        return IRFuncDecl(self.name, child_body, self.num_params) if child_body != self.body else self


class IRCompUnit(IRNode):
    name: str
    functions: Dict[str, IRFuncDecl]

    def __init__(self, name: str, functions = {}):
        self.name = name
        self.functions = functions

    def __repr__(self):
        return "COMPUNIT"

    def visit_children(self, visitor):
        child_funcs = [visitor.visit(self, func) for _, func in self.functions]

        if any(func != child_funcs[i] for i, func in enumerate(self.functions)):
            return IRCompUnit(self.name, child_funcs)

        return self
