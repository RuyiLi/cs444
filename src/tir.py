from __future__ import annotations

from functools import reduce
from typing import Dict, List, Literal, Tuple, TypeVar, TYPE_CHECKING

if TYPE_CHECKING:
    from joos_types import SymbolType

from context import ReferenceType, PrimitiveType

T = TypeVar("T")


class IRNode:
    label: str
    children: List[IRNode]

    def __init__(self, children=None):
        self.children = children if children is not None else []

    def visit_children(self, visitor):
        return self

    def aggregate_children(self, visitor):
        return reduce(lambda a, c: visitor.bind(a, visitor.visit(self, c)), self.children, visitor.unit())

    def __repr__(self):
        return str(self)


class IRStmt(IRNode):
    def __str__(self) -> str:
        return "EMPTY"


class IRExpr(IRNode):
    is_constant: bool

    def __init__(self, children=[], is_constant=False):
        super().__init__(children)
        self.is_constant = is_constant


class IRComment(IRStmt):
    comment: str

    def __init__(self, comment: str):
        super().__init__()
        self.comment = comment

    def __str__(self):
        return f"COMMENT({self.comment})"


class IRConst(IRExpr):
    value: int | Literal["null"]

    def __init__(self, value: int | Literal["null"]):
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
    arg_types: List[str]
    is_ctor: bool

    def __init__(
        self,
        target: IRExpr,
        args: List[IRExpr] = [],
        arg_types: List[str] = [],
        is_ctor: bool = False,
    ):
        super().__init__([target] + args)
        self.target = target
        self.args = args
        self.arg_types = arg_types
        self.is_ctor = is_ctor

    def __str__(self):
        return f"CALL(target={self.target}, args=[{','.join(map(str, self.args))}], arg_types=[{','.join(self.arg_types)}])"

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

    def __init__(self, stmts: List[IRStmt], replace_parent=False):
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

    def __init__(self, cond: IRExpr, true_label: IRName, false_label=None):
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
    modifiers: List[str]
    return_type: SymbolType
    body: IRStmt
    params: List[str]
    local_vars: Dict[str, SymbolType]
    formal_param_types: List[PrimitiveType | ReferenceType]
    is_constructor: bool
    actual_local_var_decls: List[str]

    def __init__(
        self,
        name: str,
        modifiers: List[str],
        return_type: SymbolType,
        body: IRStmt,
        params: List[str],
        local_vars: Dict[str, SymbolType],
        formal_param_types: List[PrimitiveType | ReferenceType],
        is_constructor: bool = False,
        actual_local_var_decls: List[str] = None,
    ):
        super().__init__([body])
        self.name = name
        self.modifiers = modifiers
        self.return_type = return_type
        self.body = body
        self.params = params
        self.local_vars = local_vars
        self.formal_param_types = formal_param_types
        self.is_constructor = is_constructor
        self.actual_local_var_decls = actual_local_var_decls or []

        self.actual_local_var_decls.extend(self.params)

    def __str__(self):
        return f"FuncDecl({self.name}, {self.body})"

    def visit_children(self, visitor):
        child_body = visitor.visit(self, self.body)
        return (
            IRFuncDecl(
                self.name,
                self.modifiers,
                self.return_type,
                child_body,
                self.params,
                self.local_vars,
                self.formal_param_types,
                self.is_constructor,
                self.actual_local_var_decls,
            )
            if child_body != self.body
            else self
        )


class IRFieldDecl(IRNode):
    name: str
    modifiers: List[str]
    field_type: SymbolType
    expr: IRExpr
    canonical: Tuple[IRStmt, IRExpr] | None

    def __init__(
        self,
        name: str,
        modifiers: List[str],
        field_type: SymbolType,
        expr: IRExpr,
        canonical: Tuple[IRStmt, IRExpr] | None = None,
    ):
        super().__init__(list(canonical) if canonical is not None else [expr])
        self.name = name
        self.modifiers = modifiers
        self.field_type = field_type
        self.expr = expr
        self.canonical = canonical

    def __str__(self):
        return f"FieldDecl({self.name}, {self.expr})"

    def visit_children(self, visitor):
        if self.canonical:
            stmt, expr = self.canonical
            child_stmt = visitor.visit(self, stmt)
            child_expr = visitor.visit(self, expr)

            if child_stmt != stmt or child_expr != expr:
                return IRFieldDecl(
                    self.name, self.modifiers, self.field_type, self.expr, (child_stmt, child_expr)
                )
            return self

        child_expr = visitor.visit(self, self.expr)
        return (
            IRFieldDecl(self.name, self.modifiers, self.field_type, child_expr, None)
            if child_expr != self.expr
            else self
        )

    def aggregate_children(self, visitor):
        children = self.canonical if self.canonical is not None else [self.expr]
        return reduce(lambda a, c: visitor.bind(a, visitor.visit(self, c)), children, visitor.unit())


class IRCompUnit(IRNode):
    name: str
    fields: Dict[str, IRFieldDecl]
    functions: Dict[str, IRFuncDecl]

    def __init__(self, name: str, fields: Dict[str, IRFieldDecl], functions: Dict[str, IRFuncDecl] = None):
        super().__init__(list(fields.values()) + list(functions.values()))
        self.name = name
        self.fields = fields
        self.functions = functions or {}

    def __str__(self):
        return "COMPUNIT"

    def visit_children(self, visitor):
        child_fields = dict([(name, visitor.visit(self, field)) for name, field in self.fields.items()])
        child_funcs = dict([(name, visitor.visit(self, func)) for name, func in self.functions.items()])

        if any(field != child_fields[name] for name, field in self.fields) or any(
            func != child_funcs[name] for name, func in self.functions
        ):
            return IRCompUnit(self.name, child_fields, child_funcs)

        return self
