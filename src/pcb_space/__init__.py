"""pcb-space: electrical/mechanical intent in, KiCad geometry out."""

from .compile import CompiledJob, compile_design
from .language import Board, Keepout, NetReq, Place, load_place_file
from .model import BoardSpec, Design

__version__ = "0.1.0"
__all__ = [
    "Board",
    "BoardSpec",
    "CompiledJob",
    "Design",
    "Keepout",
    "NetReq",
    "Place",
    "compile_design",
    "load_place_file",
]
