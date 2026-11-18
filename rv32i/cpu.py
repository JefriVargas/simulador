"""Estado y ciclo de instrucción: fetch → decode → execute → commit."""

from dataclasses import dataclass
from pathlib import Path

from .isa import Instruction, IllegalInstruction, alu, branch_taken, decode, sx, u32
from .memory import Memory, MemoryFault, SIZE

DEFAULT_SP = 0x00100000
MAX_IMAGE = 64 << 20
LOAD_SPEC = {"lb": (1, True), "lh": (2, True), "lw": (4, False),
             "lbu": (1, False), "lhu": (2, False)}
STORE_WIDTH = {"sb": 1, "sh": 2, "sw": 4}


class ExecutionFault(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class StepResult:
    pc: int
    word: int
    instruction: Instruction
    next_pc: int
    reg_write: tuple[int, int, int] | None
    mem_write: tuple[int, bytes, bytes] | None


def aligned(addr: int, width: int, purpose: str) -> None:
    if addr % width:
        raise MemoryFault(f"{purpose}: dirección desalineada 0x{addr:08X} (alineación de {width} bytes)")


class CPU:
    def __init__(self, initial_sp: int = DEFAULT_SP) -> None:
        if not (0 <= initial_sp < SIZE and initial_sp % 16 == 0):
            raise ValueError("sp inicial debe ser una dirección de 32 bits alineada a 16")
        self.initial_sp = initial_sp
        self.image = b""
        self.reset()

    def reset(self) -> None:
        self.pc = self.steps = 0
        self._regs = [0] * 32
        self._regs[2] = self.initial_sp
        self.memory = Memory()
        self.memory.write(0, self.image)

    @property
    def registers(self) -> tuple[int, ...]:
        return tuple(self._regs)

    def load(self, path: str | Path) -> int:
        with Path(path).open("rb") as file:
            image = file.read(MAX_IMAGE + 1)
        self.load_image(image)
        return len(image)

    def load_image(self, image: bytes) -> None:
        if not 4 <= len(image) <= MAX_IMAGE:
            raise ValueError("el binario raw debe tener entre 4 bytes y 64 MiB")
        if image.startswith(b"\x7fELF"):
            raise ValueError("archivo ELF: exporta un binario raw antes de cargarlo")
        self.image = bytes(image)
        self.reset()

    def step(self) -> StepResult:
        if not self.image:
            raise ExecutionFault("carga un archivo raw primero")
        pc = self.pc
        try:
            aligned(pc, 4, "fetch")
            word = self.memory.read_int(pc, 4)
            ins = decode(word)
            a, b = self._regs[ins.rs1], self._regs[ins.rs2]
            next_pc = u32(pc + 4)
            value = None
            memory_write = None
            match ins.form:
                case "R" | "I":
                    value = alu(ins.op, a, b if ins.form == "R" else ins.imm)
                case "L":
                    addr = u32(a + ins.imm)
                    width, signed = LOAD_SPEC[ins.op]
                    aligned(addr, width, ins.op)
                    raw = self.memory.read_int(addr, width)
                    value = sx(raw, width * 8) if signed else raw
                case "S":
                    addr = u32(a + ins.imm)
                    width = STORE_WIDTH[ins.op]
                    aligned(addr, width, ins.op)
                    data = b.to_bytes(4, "little")[:width]
                    memory_write = (addr, self.memory.read(addr, width), data)
                case "B":
                    if branch_taken(ins.op, a, b):
                        next_pc = u32(pc + ins.imm)
                case "J" | "JR":
                    value = next_pc
                    next_pc = u32(pc + ins.imm) if ins.form == "J" else u32(a + ins.imm) & ~1
                case "U":
                    value = ins.imm if ins.op == "lui" else pc + ins.imm
                case _:
                    raise AssertionError(ins.form)
            aligned(next_pc, 4, ins.op)
        except (IllegalInstruction, MemoryFault) as exc:
            raise ExecutionFault(f"PC=0x{pc:08X}: {exc}") from exc

        # Los fallos de ejecución anteriores no modifican el estado.
        reg_write = None
        if memory_write is not None:
            addr, _, data = memory_write
            self.memory.write(addr, data)
        if value is not None and ins.rd:
            result = u32(value)
            reg_write = (ins.rd, self._regs[ins.rd], result)
            self._regs[ins.rd] = result
        self.pc = next_pc
        self.steps += 1
        return StepResult(pc, word, ins, next_pc, reg_write, memory_write)
