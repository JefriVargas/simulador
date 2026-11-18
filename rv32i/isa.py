"""Decodificación y operaciones puras de RV32I."""

from dataclasses import dataclass

MASK = 0xFFFFFFFF


def u32(value: int) -> int:
    return value & MASK


def sx(value: int, width: int) -> int:
    """Interpreta un patrón de width bits como entero con signo."""
    sign = 1 << (width - 1)
    return (value ^ sign) - sign


class IllegalInstruction(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Instruction:
    op: str
    form: str
    rd: int
    rs1: int
    rs2: int
    imm: int = 0

    def __str__(self) -> str:
        d, a, b = (f"x{i}" for i in (self.rd, self.rs1, self.rs2))
        imm = self.imm
        match self.form:
            case "R": args = f"{d}, {a}, {b}"
            case "I": args = f"{d}, {a}, {imm}"
            case "L" | "JR": args = f"{d}, {imm}({a})"
            case "S": args = f"{b}, {imm}({a})"
            case "B": args = f"{a}, {b}, {imm:+d}"
            case "J": args = f"{d}, {imm:+d}"
            case "U": args = f"{d}, 0x{imm >> 12:05X}"
            case _: raise AssertionError(self.form)
        return f"{self.op} {args}"


# Claves exactas: no aceptar MUL ni funct7 reservados como operaciones base.
REG = {
    (0, 0): "add", (0, 0x20): "sub", (1, 0): "sll", (2, 0): "slt",
    (3, 0): "sltu", (4, 0): "xor", (5, 0): "srl", (5, 0x20): "sra",
    (6, 0): "or", (7, 0): "and",
}
IMM = {0: "addi", 2: "slti", 3: "sltiu", 4: "xori", 6: "ori", 7: "andi"}
SHIFT = {(1, 0): "slli", (5, 0): "srli", (5, 0x20): "srai"}
LOAD = {0: "lb", 1: "lh", 2: "lw", 4: "lbu", 5: "lhu"}
STORE = {0: "sb", 1: "sh", 2: "sw"}
BRANCH = {0: "beq", 1: "bne", 4: "blt", 5: "bge", 6: "bltu", 7: "bgeu"}


def decode(word: int) -> Instruction:
    op = word & 0x7F
    rd = (word >> 7) & 31
    f3 = (word >> 12) & 7
    rs1 = (word >> 15) & 31
    rs2 = (word >> 20) & 31
    f7 = word >> 25
    imm_i = sx(word >> 20, 12)
    try:
        match op:
            case 0x33:
                return Instruction(REG[f3, f7], "R", rd, rs1, rs2)
            case 0x13:
                name, imm = (SHIFT[f3, f7], rs2) if f3 in (1, 5) else (IMM[f3], imm_i)
                return Instruction(name, "I", rd, rs1, rs2, imm)
            case 0x03:
                return Instruction(LOAD[f3], "L", rd, rs1, rs2, imm_i)
            case 0x23:
                return Instruction(STORE[f3], "S", rd, rs1, rs2, sx((f7 << 5) | rd, 12))
            case 0x63:
                imm = ((word >> 31) << 12) | ((rd & 1) << 11) | ((f7 & 63) << 5) | (rd & 30)
                return Instruction(BRANCH[f3], "B", rd, rs1, rs2, sx(imm, 13))
            case 0x37 | 0x17:
                return Instruction("lui" if op == 0x37 else "auipc", "U", rd, rs1, rs2, word & 0xFFFFF000)
            case 0x67 if f3 == 0:
                return Instruction("jalr", "JR", rd, rs1, rs2, imm_i)
            case 0x6F:
                imm = ((word >> 31) << 20) | (word & 0xFF000) | ((word >> 9) & 0x800) | ((word >> 20) & 0x7FE)
                return Instruction("jal", "J", rd, rs1, rs2, sx(imm, 21))
    except KeyError:
        pass
    raise IllegalInstruction(f"instrucción no soportada 0x{word:08X} (opcode 0x{op:02X})")


def alu(op: str, a: int, b: int) -> int:
    match op:
        case "add" | "addi": return a + b
        case "sub": return a - b
        case "sll" | "slli": return a << (b & 31)
        case "srl" | "srli": return a >> (b & 31)
        case "sra" | "srai": return sx(a, 32) >> (b & 31)
        case "slt" | "slti": return int(sx(a, 32) < sx(u32(b), 32))
        case "sltu" | "sltiu": return int(a < u32(b))
        case "and" | "andi": return a & b
        case "or" | "ori": return a | b
        case "xor" | "xori": return a ^ b
        case _: raise AssertionError(op)


def branch_taken(op: str, a: int, b: int) -> bool:
    match op:
        case "beq": return a == b
        case "bne": return a != b
        case "blt": return sx(a, 32) < sx(b, 32)
        case "bge": return sx(a, 32) >= sx(b, 32)
        case "bltu": return a < b
        case "bgeu": return a >= b
        case _: raise AssertionError(op)
