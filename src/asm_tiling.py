from typing import Dict, List
from tir import IRBinExpr, IRConst, IRMove, IRReturn, IRSeq, IRStmt, IRExpr, IRTemp

def tile_stmt(stmt: IRStmt, local_var_dict: Dict[str, int]) -> List[str]:
	match stmt:
		case IRMove(target=t, source=s):
			match t:
				case IRTemp(name=n):
					if (loc := local_var_dict.get(n, None)) is not None:
						stmts = tile_expr(s, "edx", local_var_dict)
						return stmts + [f"mov [ebp-{loc*4}], edx"]

					local_var_dict[n] = len(local_var_dict.keys())
					stmts = tile_expr(s, "edx", local_var_dict)
					return stmts + [f"push edx"]

				case IRMem(address=a):
					pass

		case IRReturn(ret=ret):
			if stmt.ret is None:
				return []

			stmts = tile_expr(stmt.ret, 'eax', local_var_dict)
			return stmts + ['ret']

		case IRSeq(stmts=ss):
			asm = []
			for s in ss:
				asm += tile_stmt(s, local_var_dict)
				print(local_var_dict, asm)
			return asm

	return []

def tile_expr(expr: IRExpr, output_reg: str, local_var_dict: Dict[str, int]) -> List[str]:
	asm = []
	hold = ""

	print('tiling expr', expr)

	match expr:
		case IRConst(value=v):
			hold = v

		case IRBinExpr(op_type=o, left=l, right=r):
			if isinstance(l, IRTemp):
				left = local_var_dict.get(l.name)

				if isinstance(r, IRTemp):
					right = local_var_dict.get(r.name)
				elif isinstance(r, IRConst):
					right = r.value

				asm += [f"{o.lower()} [ebp-{4*left}], {right}"]
				hold=f"[ebp-{4*left}]"

		case IRTemp(name=n):
			if (loc := local_var_dict.get(n, None)) is not None:
				hold = f"[ebp-{loc*4}]"
			else:
				print(local_var_dict.get(n, None))
				print(local_var_dict)
				raise Exception(f"couldn't find local var {n} in dict!")
		case x:
			print('unknown expr type', x);

	return asm + [f"mov {output_reg}, {hold}"]



# SEQ(
# MOVE(target=TEMP(correct), source=CONST(0)),
# MOVE(target=TEMP(136037886784608), source=TEMP(correct)),
# MOVE(target=TEMP(correct), source=(TEMP(136037886784608) ADD CONST(5))),
# RETURN(TEMP(correct)))