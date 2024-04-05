import logging
from functools import reduce
from typing import Dict, List, Tuple

from tir import (
	IRBinExpr,
	IRCall,
	IRCJump,
	IRConst,
	IRExpr,
	IRFuncDecl,
	IRJump,
	IRLabel,
	IRMem,
	IRMove,
	IRName,
	IRReturn,
	IRSeq,
	IRStmt,
	IRTemp,
)


def tile_func(func: IRFuncDecl) -> List[str]:
	asm = []

	if func.name == "test":
		asm += [
			"global _start",
			"_start:"
		]
	else:
		asm += [
			f"_{func.name}:",
			"push ebp"			# Save old base pointer
		]

	asm += ["mov ebp, esp"]		# Update base pointer to start in this call frame

	# Parameters are behind the return address on the stack, so we make them -2
	local_var_dict = dict([(param, -(i+2)) for i, param in enumerate(func.params)])
	local_var_dict['%RET'] = -100

	asm += tile_stmt(func.body, local_var_dict)

	if func.name != "test":
		return asm

	main_return = [
		"mov ebx, eax",		# Save final return
		"mov eax, 1",		# sys_exit
		"int 0x80"
	]

	# Replace "ret" with special returns in main function
	return reduce(lambda a, c: a + ([c] if c != "ret" else main_return), asm, [])


def fmt_bp(index: int):
	if index is None:
		raise Exception('Attempted to format with None index!')

	if index == -100:
		return "eax"

	if index < 0:
		return f"[ebp+{-4*index}]"

	index += 1
	return f"[ebp-{4*index}]"


def process_expr(expr: IRExpr, local_var_dict: Dict[str, int]) -> Tuple[str | int, List[str]]:
	logging.info(f"processing expr {expr}, {local_var_dict}")
	if isinstance(expr, IRTemp):
		return ("ecx", [f"mov ecx, {fmt_bp(local_var_dict.get(expr.name))}"])

	if isinstance(expr, IRConst):
		return (expr.value, [])

	if isinstance(expr, IRBinExpr):
		return ("ecx", tile_expr(expr, "ecx", local_var_dict))

	raise Exception(f"unable to process expr {expr}")


def tile_stmt(stmt: IRStmt, local_var_dict: Dict[str, int]) -> List[str]:
	logging.info(f"tiling stmt {stmt}")

	match stmt:
		case IRCall(target=t, args=args):
			asm = []

			for arg in args:
				r, r_asm = process_expr(arg, local_var_dict)
				asm += r_asm + [f"push {r}"]

			asm += [
				f"call _{t.name.split('.')[-1]}",	# FIX: Hack to try and call local function
				f"add esp, {len(args)*4}"	# pop off arguments
			]
			return asm

		case IRCJump(cond=c, true_label=t):
			match c:
				case IRConst(value=v):
					if v == 0:	# never jump
						return []
					if v == 1:	# always jump
						return [f"jmp {t.name}"]

					raise Exception(f"CJump with constant value {v} not 0 or 1!!")

				case IRTemp(name=n):
					if (loc := local_var_dict.get(n, None)) is not None:
						return [
							f"mov eax, {fmt_bp(loc)}",
							"cmp eax, 1",
							f"je {t.name}"
						]
					raise Exception(f"CJump with unbound variable {n}")

				case IRBinExpr(op_type=o, left=l, right=r):
					asm = []
					assert isinstance(l, IRTemp)

					left = local_var_dict.get(l.name)

					right, r_asm = process_expr(r, local_var_dict)
					asm += r_asm

					match o:
						case "EQ":
							return asm + [
								f"mov edx, {fmt_bp(left)}",
								f"cmp edx, {right}",
								f"je {t.name}"
							]

				case x:
					raise Exception(f"CJump with unimplemented condition {c}")

		case IRJump(target=t):
			assert isinstance(t, IRName)
			return [f"jmp {t.name}"]

		case IRLabel(name=n):
			return [f"{n}:"]

		case IRMove(target=t, source=s):
			match t:
				case IRTemp(name=n):
					if (loc := local_var_dict.get(n, None)) is not None:
						logging.info("VARIABLE", n, "EXISTS AT", loc)
						r, r_asm = process_expr(s, local_var_dict)
						return r_asm + [f"mov {fmt_bp(loc)}, {r}"]

					local_var_dict[n] = len([v for v in local_var_dict.values() if v >= 0])
					logging.info(f"CREATING NEW VAR {n} AT LOC {local_var_dict[n]}")
					r, r_asm = process_expr(s, local_var_dict)
					return r_asm + [f"push {r}"]

				case IRMem(address=a):
					pass

		case IRReturn(ret=ret):
			if stmt.ret is None:
				return []

			# Return always uses eax register
			stmts = tile_expr(stmt.ret, "eax", local_var_dict)
			return stmts + [f"mov esp, ebp", "pop ebp", "ret"]

		case IRSeq(stmts=ss):
			asm = []
			for s in ss:
				asm += tile_stmt(s, local_var_dict)
			return asm

		case x:
			raise Exception(f"Unknown tiling for statement {x}")

	return []


def tile_expr(expr: IRExpr, output_reg: str, local_var_dict: Dict[str, int]) -> List[str]:
	asm = []
	hold = ""

	logging.info('tiling expr', expr)

	match expr:
		case IRConst(value=v):
			hold = v

		case IRBinExpr(op_type=o, left=l, right=r):
			assert isinstance(l, IRTemp)

			left = local_var_dict.get(l.name)

			right, r_asm = process_expr(r, local_var_dict)
			asm += r_asm

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
			logging.info
			if (loc := local_var_dict.get(n, None)) is not None:
				hold = fmt_bp(loc)
			else:
				logging.info(local_var_dict.get(n, None))
				logging.info(local_var_dict)
				raise Exception(f"couldn't find local var {n} in dict!")
		case x:
			logging.info('unknown expr type', x)

	if output_reg != hold:
		asm += [f"mov {output_reg}, {hold}"]

	logging.info(asm)
	return asm
