import os
import subprocess
import sys
import unittest
from pathlib import Path

from rv32i.cpu import CPU, DEFAULT_SP, ExecutionFault
from rv32i.isa import REG, IMM, SHIFT, LOAD, STORE, BRANCH
from rv32i.memory import Memory, MemoryFault

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "ejemplos"
EXPECTED_EXAMPLES = {"basico": (0x14, 5), "riscvtest": (0x50, 18),
                     "quicksort": (0x50, 609), "arbol": (0x4C, 152)}


def raw(*words):
    return b"".join(word.to_bytes(4, "little") for word in words)


# Codificaciones de prueba: construyen palabras de máquina, sin usar el decoder.
def r(f3, f7=0, rd=5, a=3, b=4):
    return 0x33 | rd << 7 | f3 << 12 | a << 15 | b << 20 | f7 << 25


def i(f3, imm, rd=5, a=3, op=0x13):
    return op | rd << 7 | f3 << 12 | a << 15 | (imm & 4095) << 20


def s(f3, imm, a=3, b=4):
    hi, lo = divmod(imm & 4095, 32)
    return 0x23 | lo << 7 | f3 << 12 | a << 15 | b << 20 | hi << 25


def branch(f3, imm, a=3, b=4):
    v = imm & 8191
    return (0x63 | ((v >> 11) & 1) << 7 | ((v >> 1) & 15) << 8 | f3 << 12
            | a << 15 | b << 20 | ((v >> 5) & 63) << 25 | (v >> 12) << 31)


def jal(imm, rd=5):
    v = imm & 0x1FFFFF
    return (0x6F | rd << 7 | ((v >> 12) & 255) << 12 | ((v >> 11) & 1) << 20
            | ((v >> 1) & 1023) << 21 | (v >> 20) << 31)


# name, word, x3, x4, x5 esperado; patrones escogidos para separar signo y overflow.
ALU = [
    ("add", r(0), 0xFFFFFFFF, 2, 1),
    ("sub", r(0, 32), 0, 1, 0xFFFFFFFF),
    ("sll", r(1), 1, 63, 0x80000000),
    ("slt", r(2), 0x80000000, 1, 1),
    ("sltu", r(3), 0x80000000, 1, 0),
    ("xor", r(4), 0xF0, 0xCC, 0x3C),
    ("srl", r(5), 0x80000000, 33, 0x40000000),
    ("sra", r(5, 32), 0x80000000, 33, 0xC0000000),
    ("or", r(6), 0xF0, 0xCC, 0xFC),
    ("and", r(7), 0xF0, 0xCC, 0xC0),
    ("addi", i(0, -2048), 0x80000000, 0, 0x7FFFF800),
    ("slli", i(1, 31), 3, 0, 0x80000000),
    ("slti", i(2, -1), 0xFFFFFFFE, 0, 1),
    ("sltiu", i(3, -1), 0x80000000, 0, 1),
    ("xori", i(4, -1), 0xAAAAAAAA, 0, 0x55555555),
    ("srli", i(5, 31), 0x80000000, 0, 1),
    ("srai", i(5, 1024 + 31), 0x80000000, 0, 0xFFFFFFFF),
    ("ori", i(6, -2048), 0x43, 0, 0xFFFFF843),
    ("andi", i(7, 255), 0x12345678, 0, 0x78),
]
LOADS = [
    ("lb", 0, 0xFFFFFF81), ("lh", 1, 0xFFFFFE81), ("lw", 2, 0x1234FE81),
    ("lbu", 4, 0x81), ("lhu", 5, 0xFE81),
]
STORES = [
    ("sb", 0, "78 ab ab ab"), ("sh", 1, "78 56 ab ab"), ("sw", 2, "78 56 34 12"),
]
BRANCHES = [
    ("beq", 0, (3, 3), (3, 4)), ("bne", 1, (3, 4), (3, 3)),
    ("blt", 4, (0xFFFFFFFF, 0), (0, 0xFFFFFFFF)),
    ("bge", 5, (0, 0xFFFFFFFF), (0xFFFFFFFF, 0)),
    ("bltu", 6, (0, 0xFFFFFFFF), (0xFFFFFFFF, 0)),
    ("bgeu", 7, (0xFFFFFFFF, 0), (0, 0xFFFFFFFF)),
]


class InstructionTests(unittest.TestCase):
    def setUp(self):
        self.coverage = set()

    def run_one(self, word, *, pc=0, a=0, b=0, data=None):
        cpu = CPU()
        cpu.load_image(raw(0x13))
        cpu.memory.write(pc, raw(word))
        cpu.pc = pc
        # Inicializar vectores de prueba sin codificar una segunda instrucción.
        cpu._regs[3:5] = [a, b]
        if data:
            cpu.memory.write(data[0], bytes.fromhex(data[1]))
        result = cpu.step()
        self.coverage.add(result.instruction.op)
        self.assertEqual((result.pc, result.word, cpu.steps, cpu.registers[0]), (pc, word, 1, 0))
        return cpu

    def test_anexo_a_completo(self):
        for op, word, a, b, expected in ALU:
            with self.subTest(op=op):
                cpu = self.run_one(word, a=a, b=b)
                self.assertEqual((cpu.registers[5], cpu.pc), (expected, 4))
        for op, f3, expected in LOADS:
            with self.subTest(op=op):
                cpu = self.run_one(i(f3, -4, op=3), a=0x104, data=(0x100, "81 fe 34 12"))
                self.assertEqual((cpu.registers[5], cpu.pc), (expected, 4))
        for op, f3, expected in STORES:
            with self.subTest(op=op):
                cpu = self.run_one(s(f3, -4), a=0x104, b=0x12345678, data=(0x100, "ab ab ab ab"))
                self.assertEqual(cpu.memory.read(0x100, 4), bytes.fromhex(expected))
                self.assertEqual(cpu.pc, 4)
        for op, f3, yes, no in BRANCHES:
            with self.subTest(op=op):
                self.assertEqual(self.run_one(branch(f3, -8), pc=0x80, a=yes[0], b=yes[1]).pc, 0x78)
                self.assertEqual(self.run_one(branch(f3, 2), pc=0x80, a=no[0], b=no[1]).pc, 0x84)
        self.assertEqual(self.run_one(0xABCDE2B7).registers[5], 0xABCDE000)  # lui
        self.assertEqual(self.run_one(0xFFFFF297, pc=0x1004).registers[5], 4)  # auipc
        cpu = self.run_one(jal(-0xA82C), pc=0xB000)
        self.assertEqual((cpu.pc, cpu.registers[5]), (0x7D4, 0xB004))
        cpu = self.run_one(i(0, -3, rd=3, op=0x67), pc=0x100, a=0x184)
        self.assertEqual((cpu.pc, cpu.registers[3]), (0x180, 0x104))
        expected_names = (set(REG.values()) | set(IMM.values()) | set(SHIFT.values())
                          | set(LOAD.values()) | set(STORE.values()) | set(BRANCH.values())
                          | {"lui", "auipc", "jal", "jalr"})
        self.assertEqual(len(expected_names), 37)
        self.assertEqual(self.coverage, expected_names)

    def test_wrap_x0_y_extremos_de_inmediato(self):
        self.assertEqual(self.run_one(i(0, 7, rd=0)).registers[0], 0)
        cpu = self.run_one(i(0, 1), pc=0xFFFFFFFC, a=0xFFFFFFFF)
        self.assertEqual((cpu.pc, cpu.registers[5]), (0, 0))
        self.assertEqual(self.run_one(branch(0, -4096)).pc, 0xFFFFF000)
        self.assertEqual(self.run_one(branch(0, 4092)).pc, 4092)
        self.assertEqual(self.run_one(jal(-1048576)).pc, 0xFFF00000)
        self.assertEqual(self.run_one(jal(1048572, rd=0)).pc, 1048572)
        self.assertEqual(self.run_one(s(0, -1), b=9).memory.read(0xFFFFFFFF, 1), b"\x09")
        cpu = self.run_one(i(4, 1, op=3), pc=4, a=0xFFFFFFFF, data=(0, "a5"))
        self.assertEqual(cpu.registers[5], 0xA5)
        self.assertEqual(self.run_one(r(5, 32), a=0x80000000, b=32).registers[5], 0x80000000)

    def test_errores_preservan_estado_y_carga_a_x0_verifica_direccion(self):
        cases = [
            (0, "no soportada"), (0x00000073, "no soportada"),
            (r(0, 1), "no soportada"), (i(1, 32), "no soportada"),
            (i(1, 0, op=0x67), "no soportada"), (branch(2, 4), "no soportada"),
            (i(2, 1, rd=0, op=3), "desalineada"), (s(1, 1), "desalineada"),
            (branch(0, 2), "desalineada"), (jal(2), "desalineada"),
            (i(0, 3, op=0x67), "desalineada"),
        ]
        cpu = CPU()
        with self.assertRaisesRegex(ExecutionFault, "carga"):
            cpu.step()
        for word, error in cases:
            with self.subTest(word=hex(word)):
                image = raw(word)
                cpu.load_image(image)
                with self.assertRaisesRegex(ExecutionFault, f"PC=0x00000000.*{error}"):
                    cpu.step()
                self.assertEqual((cpu.steps, cpu.pc, cpu.registers), (0, 0, (0, 0, DEFAULT_SP) + (0,) * 29))
                self.assertEqual(cpu.memory.read(0, 4), image)


class IntegrationTests(unittest.TestCase):
    def test_ram_cruza_bloques_y_valida_rango_completo(self):
        mem = Memory()
        mem.write(4094, b"\x78\x56\x34\x12")
        self.assertEqual(mem.read_int(4094, 4), 0x12345678)
        self.assertEqual(mem.read(4093, 6), b"\x00\x78\x56\x34\x12\x00")
        mem.write(0xFFFFFFFF, b"\xAA")
        with self.assertRaises(MemoryFault):
            mem.write(0xFFFFFFFF, b"\xBB\xCC")
        self.assertEqual(mem.read(0xFFFFFFFF, 1), b"\xAA")
        self.assertEqual(mem.read_int(0x80000000, 4), 0)

    def test_reinicio_y_carga_invalida_no_pierde_programa(self):
        cpu = CPU(0x2000)
        cpu.load(EXAMPLES / "basico.bin")
        cpu.step()
        for invalid in (b"", b"\x7fELF" + bytes(8)):
            with self.assertRaises(ValueError):
                cpu.load_image(invalid)
        self.assertEqual((cpu.pc, cpu.registers[2], cpu.registers[5]), (4, 0x2000, 5))
        cpu.memory.write(0x64, b"\x0c")
        cpu.reset()
        self.assertEqual((cpu.pc, cpu.registers[5], cpu.memory.read_int(100, 4)), (0, 0, 0))
        self.assertEqual(cpu.memory.read(0, len(cpu.image)), cpu.image)

    def test_fetch_de_codigo_escrito_fuera_del_archivo_y_pc_invalido(self):
        cpu = CPU()
        cpu.load_image(raw(jal(0x1000, rd=0)))
        cpu.memory.write(0x1000, raw(i(0, 9)))
        self.assertEqual(cpu.step().next_pc, 0x1000)
        cpu.step()
        self.assertEqual(cpu.registers[5], 9)
        with self.assertRaisesRegex(ExecutionFault, "0x00001004.*no soportada"):
            cpu.step()
        cpu.pc = 2
        with self.assertRaisesRegex(ExecutionFault, "fetch.*desalineada"):
            cpu.step()

    def test_cuatro_programas_ensamblados(self):
        for name, (stop_pc, expected_steps) in EXPECTED_EXAMPLES.items():
            with self.subTest(name=name):
                cpu = CPU()
                path = EXAMPLES / f"{name}.bin"
                cpu.load(path)
                self.assertEqual(cpu.memory.read(0, len(cpu.image)), path.read_bytes())
                while cpu.pc != stop_pc and cpu.steps < 5000:
                    cpu.step()
                self.assertEqual(cpu.pc, stop_pc)
                # Comprobar que el punto final corresponde al bucle del programa.
                self.assertEqual(cpu.steps, expected_steps)
                self.assertEqual(cpu.step().next_pc, stop_pc)
                if name == "basico":
                    self.assertEqual(cpu.registers[5:9], (5, 7, 12, 12))
                    self.assertEqual(cpu.memory.read(100, 4), bytes.fromhex("0C 00 00 00"))
                elif name == "riscvtest":
                    self.assertEqual(cpu.memory.read_int(96, 4), 7)
                    self.assertEqual(cpu.memory.read_int(100, 4), 25)
                else:
                    self.assertEqual(cpu.registers[2], 0x10000)
                    words = [cpu.memory.read_int(0x1000 + 4 * idx, 4) for idx in range(7)]
                    self.assertEqual(words, [1, 2, 3, 4, 6, 8, 9] if name == "quicksort" else [6, 4, 4, 1, 2, 2, 1])
                    if name == "arbol":
                        self.assertEqual(cpu.registers[10], 1)

    def test_cli_demo_y_codigo_de_salida_en_error(self):
        demo = subprocess.run([sys.executable, "-B", "-m", "rv32i", "--script", "ejemplos/demo.txt"],
                              cwd=ROOT, capture_output=True, encoding="utf-8",
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"}, check=True)
        self.assertEqual(demo.stdout.count("PC objetivo alcanzado"), 3)
        self.assertIn("0x00000064: 0C 00 00 00", demo.stdout)
        self.assertIn("0x00000064: 0x00000019  (25)", demo.stdout)
        self.assertRegex(demo.stdout, r"x10\s+\(\s*a0\) = 0x00000001")
        error = subprocess.run([sys.executable, "-B", "-m", "rv32i", "missing.bin"],
                               cwd=ROOT, capture_output=True)
        self.assertEqual(error.returncode, 1)
        self.assertIn(b"Error:", error.stderr)


if __name__ == "__main__":
    unittest.main()
