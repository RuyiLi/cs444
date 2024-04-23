import logging

from tir import (
    IRCompUnit,
)

log = logging.getLogger(__name__)


def register_allocation(comp_unit: IRCompUnit):
    pass

def no_optimization(comp_unit: IRCompUnit):
    return comp_unit