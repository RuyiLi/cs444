from __future__ import annotations

import logging
from typing import Generic, Optional, TypeVar

from tir import IRCall, IRCJump, IRESeq, IRExp, IRExpr, IRNode, IRSeq
log = logging.getLogger(__name__)

class IRVisitor:
    def visit(self, parent: IRNode, node: IRNode) -> IRNode:
        overrideValue = self.override(parent, node)
        if overrideValue is not None:
            return overrideValue

        v_ = self.enter(parent, node)
        if v_ is None:
            raise Exception("IRVisitor.enter() returned null!")

        child_prod_node = node.visit_children(v_)
        if child_prod_node is None:
            raise Exception("IRVisitor.visitChildren() returned null!")

        n_ = self.leave(parent, node, child_prod_node, v_)
        if n_ is None:
            raise Exception("IRVisitor.leave() returned null!")

        return n_

    def override(self, parent: IRNode, node: IRNode) -> Optional[IRNode]:
        return None

    def enter(self, parent: IRNode, node: IRNode) -> IRVisitor:
        return self

    def leave(
        self, parent: IRNode, original: IRNode, child_prod_node: IRNode, enter_visitor: IRVisitor
    ) -> IRNode:
        return child_prod_node


T = TypeVar("T")


class AggregateVisitor(Generic[T]):
    def unit(self) -> T:
        pass

    def bind(self, r1: T, r2: T) -> T:
        pass

    def visit(self, parent: IRNode, node: IRNode):
        if node is None:
            return None

        overrideValue = self.override(parent, node)
        if overrideValue is not None:
            return overrideValue

        v_ = self.enter(parent, node)
        if v_ is None:
            raise Exception("AggregateVisitor.enter() returned null!")

        child_prod = node.aggregate_children(v_)
        if child_prod is None:
            raise Exception("AggregateVisitor.visitChildren() returned null!")

        n_ = self.leave(parent, node, child_prod, v_)
        if n_ is None:
            raise Exception("AggregateVisitor.leave() returned null!")

        return n_

    def override(self, parent: IRNode, node: IRNode) -> Optional[T]:
        return None

    def enter(self, parent: IRNode, node: IRNode) -> AggregateVisitor:
        return self

    def leave(self, parent: IRNode, original: IRNode, child_prod: T, enter_visitor: AggregateVisitor) -> T:
        return child_prod


class CanonicalVisitor(AggregateVisitor[bool]):
    in_seq: bool
    in_exp: bool
    in_expr: bool
    offender: IRNode | None
    outer: CanonicalVisitor | None

    def __init__(self):
        self.in_seq = False
        self.in_exp = False
        self.in_expr = False
        self.offender = None
        self.outer = None

    def duplicate(self):
        dupe = CanonicalVisitor()
        for prop, value in vars(self).items():
            setattr(dupe, prop, value)

        return dupe

    def unit(self):
        return True

    def bind(self, r1, r2):
        return r1 and r2

    def enter(self, parent: IRNode, node: IRNode):
        if isinstance(node, IRExp):
            if self.in_exp:
                return self

            new_visitor = self.duplicate()
            new_visitor.outer = self
            new_visitor.in_exp = True
            return new_visitor

        if isinstance(node, IRExpr):
            if self.in_expr:
                return self

            new_visitor = self.duplicate()
            new_visitor.outer = self
            new_visitor.in_expr = True
            return new_visitor

        if isinstance(node, IRSeq):
            if self.in_seq:
                return self

            new_visitor = self.duplicate()
            new_visitor.outer = self
            new_visitor.in_seq = True
            return new_visitor

        return self

    def is_canonical(self, node: IRNode):
        match node:
            case IRCall():
                return not self.in_expr

            case IRCJump(false_label=f):
                return f is None

            case IRESeq():
                return False

            case IRSeq():
                return not self.in_seq

            case _:
                return True

    def leave(self, parent, original, child_prod, enter_visitor):
        if not child_prod:
            return False

        if self.is_canonical(original):
            return True

        log.info("NON CANONICAL!!")
        log.info(f"self {original}")
        log.info(f"parent {parent}")

        self.noncanonical(original if parent is None else parent)
        return False

    def noncanonical(self, offender: IRNode):
        self.offender = offender

        if self.outer is not None:
            self.outer.noncanonical(offender)
