from enum import Enum
from typing import List

class IRNode:
    label: str

    def visit_children(self, visitor):
        return self

class IRStmt(IRNode):
    pass

class IRExpr(IRNode):
    is_constant: bool

    def is_constant(self):
        return False

    def constant(self):
        raise Exception("unsupported")


class IRConst(IRExpr):
    value: int

    def __init__(self, value: int):
        self.value = value

    def __repr__(self):
        return f"CONST({self.value})"

    def is_constant(self):
        return True

    def constant(self):
        return self.value


class IRTemp(IRExpr):
    name: str

    def __init__(self, name):
        self.name = name


class IRBinExpr(IRExpr):
    op_type: str
    left: IRExpr
    right: IRExpr

    def __init__(self, op_type: str, left: IRExpr, right: IRExpr):
        self.op_type = op_type
        self.left = left
        self.right = right

    def __repr__(self):
        return self.op_type

    def visit_children(self, visitor):
        left_child = visitor.visit(self, self.left)
        right_child = visitor.visit(self, self.right)

        if left_child != self.left or right_child != self.right:
            return IRBinExpr(left_child, right_child)

        return self

    def is_constant(self):
        return self.left.is_constant() and self.right.is_constant()


class IRMem(IRExpr):
    address: IRExpr

    def __init__(self, address: IRExpr):
        self.address = address

    def __repr__(self):
        return "LABEL"

    def visit_children(self, visitor):
        child_expr = visitor.visitor(self, self.address)

        return IRMem(child_expr) if child_expr != self.address else self


class IRCall(IRExpr):
    target: IRExpr
    args: List[IRExpr]

    def __init__(self, target: IRExpr, args: List[IRExpr]):
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


class IRESeq(IRESeq):
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
