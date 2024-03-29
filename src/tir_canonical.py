from tir import IRBinExpr, IRCJump, IRCall, IRConst, IRESeq, IRExp, IRExpr, IRJump, IRLabel, IRMem, IRMove, IRName, IRReturn, IRSeq, IRStmt, IRTemp
from typing import Tuple


def canonicalize_expression(expr: IRExpr) -> Tuple[IRStmt, IRExpr]:
	if any(isinstance(expr, node_type) for node_type in [IRConst, IRTemp, IRName]):
		return (IRStmt(), expr)

	if isinstance(expr, IRMem):
		c_stmt, c_expr = canonicalize_expression(expr.address)
		return (c_stmt, IRMem(c_expr))

	if isinstance(expr, IRESeq):
		c_stmts = canonicalize_statement(expr.stmt)
		c_stmt, c_expr = canonicalize_expression(expr.expr)

		return (IRSeq([c_stmts, c_stmt]), c_expr)

	if isinstance(expr, IRBinExpr):
		cl_stmt, cl_expr = canonicalize_expression(expr.left)
		cr_stmt, cr_expr = canonicalize_expression(expr.right)

		label = f"{id(expr)}"

		return (IRSeq([cl_stmt, IRMove(IRTemp(label), cl_expr), cr_stmt]),
			IRBinExpr(expr.op_type, IRTemp(label), cr_expr))

	if isinstance(expr, IRCall):
		stmts = []
		label = f"{id(expr)}"

		for i, arg in enumerate(expr.args):
			c_stmt, c_expr = canonicalize_expression(arg)
			stmts.extend([c_stmt, IRMove(IRTemp(f"{label}_{i}"), c_expr)])

		stmts.append(IRCall(expr.target, [IRTemp(f"{label}_{i}") for i in range(len(expr.args))]))

		return (IRSeq(stmts), IRTemp("RET"))

	raise Exception(f"couldn't canonicalize expr {expr}")

def canonicalize_statement(stmt: IRStmt) -> IRStmt:
	if isinstance(stmt, IRLabel):
		return stmt

	if isinstance(stmt, IRSeq):
		return IRSeq([canonicalize_statement(s) for s in stmt.stmts])

	if isinstance(stmt, IRJump):
		c_stmt, c_expr = canonicalize_expression(stmt.target)
		return IRSeq([c_stmt, IRJump(c_expr)])

	if isinstance(stmt, IRCJump):
		c_stmt, c_expr = canonicalize_expression(stmt.cond)
		return IRSeq([c_stmt, IRCJump(c_expr, stmt.true_label, stmt.false_label)])

	if isinstance(stmt, IRExp):
		c_stmt, _ = canonicalize_expression(stmt.expr)
		return c_stmt

	if isinstance(stmt, IRReturn):
		if stmt.ret is None:
			return stmt

		c_stmt, c_expr = canonicalize_expression(stmt.ret)
		return IRSeq([c_stmt, IRReturn(c_expr)])

	if isinstance(stmt, IRMove):
		if isinstance(stmt.target, IRTemp):
			c_stmt, c_expr = canonicalize_expression(stmt.source)
			return IRSeq([c_stmt, IRMove(stmt.target, c_expr)])

		if isinstance(stmt.target, IRMem):
			ct_stmt, ct_expr = canonicalize_expression(stmt.target.address)
			cs_stmt, cs_expr = canonicalize_expression(stmt.source)

			label = f"{id(stmt)}"

			return IRSeq([ct_stmt, IRMove(IRTemp(label), ct_expr), cs_stmt, IRMove(IRMem(IRTemp(label)), cs_expr)])

	raise Exception(f"couldn't canonicalize stmt {stmt}")
