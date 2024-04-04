from typing import Dict, List
from tir import IRBinExpr, IRConst, IRFuncDecl, IRMove, IRReturn, IRSeq, IRStmt, IRExpr, IRTemp

# asm = [
# 		"push ebp",		# Save base pointer
# 		"mov ebp, esp"	# Move base pointer
# 	]

def tile_func(func: IRFuncDecl) -> List[str]:
	asm = []

	if func.name == "test":
		asm += [
			"global _start",
			"_start:",
			"mov ebp, esp"
		]

	local_var_dict = dict([(param, i) for i, param in enumerate(func.params)])
	asm += tile_stmt(func.body, local_var_dict)

	# Don't include "ret" if main function
	if func.name == "test":
		asm = list(filter(lambda x: x != "ret", asm))

		asm += [
			"mov ebx, eax",		# Save final return
			"mov eax, 1",		# sys_exit
			"int 0x80"
		]
	else:
		asm.append("pop ebp") # Restore base pointer

	return asm


def fmt_bp(index: int):
	index += 1
	return "[ebp]" if index == 0 else f"[ebp-{4*index}]"


def tile_stmt(stmt: IRStmt, local_var_dict: Dict[str, int]) -> List[str]:
	match stmt:
		case IRMove(target=t, source=s):
			match t:
				case IRTemp(name=n):
					if (loc := local_var_dict.get(n, None)) is not None:
						stmts = tile_expr(s, "edx", local_var_dict)
						return stmts + [f"mov {fmt_bp(loc)}, edx"]

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
			assert isinstance(l, IRTemp)

			left = local_var_dict.get(l.name)

			if isinstance(r, IRTemp):
				right = local_var_dict.get(r.name)
			elif isinstance(r, IRConst):
				right = r.value
			elif isinstance(r, IRBinExpr):
				asm += tile_expr(r, "edx", local_var_dict)
				right = "edx"

			asm.append(f"mov eax, {fmt_bp(left)}")

			if o == "MUL":
				asm.append(f"imul eax, {right}")

			elif o == "DIV":
				if isinstance(r, IRConst):
					asm.append(f"mov ebx, {right}")
					right = "ebx"
				asm += [
					"xor edx, edx",		# Clear out edx for division
					f"div {right}"		# Quotient stored in eax, remainder stored in edx
				]

			else:
				asm.append(f"{o.lower()} eax, {right}")

			hold = "eax"

		case IRTemp(name=n):
			if (loc := local_var_dict.get(n, None)) is not None:
				hold = fmt_bp(loc)
			else:
				print(local_var_dict.get(n, None))
				print(local_var_dict)
				raise Exception(f"couldn't find local var {n} in dict!")
		case x:
			print('unknown expr type', x)

	if output_reg != hold:
		asm += [f"mov {output_reg}, {hold}"]

	return asm
