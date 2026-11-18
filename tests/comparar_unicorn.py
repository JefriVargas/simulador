"""Contraste opcional contra Unicorn 2.1.4 (python -m tests.comparar_unicorn)."""

from unicorn import UC_ARCH_RISCV, UC_HOOK_MEM_WRITE, UC_MODE_RISCV32, Uc
from unicorn.riscv_const import UC_RISCV_REG_PC, UC_RISCV_REG_X0

from rv32i.cpu import CPU
from tests.test_rv32i import ALU, BRANCHES, EXAMPLES, EXPECTED_EXAMPLES, LOADS, STORES, branch, i, jal, raw, s

REG_IDS = list(range(UC_RISCV_REG_X0, UC_RISCV_REG_X0 + 32))
MAP_END = 0x200000


def reference(cpu, addr, code, data=None):
    ref = Uc(UC_ARCH_RISCV, UC_MODE_RISCV32)
    ref.mem_map(0, MAP_END)
    ref.mem_write(addr, code)
    ref.reg_write_batch(list(zip(REG_IDS[1:], cpu.registers[1:])))
    if data is not None:
        ref.mem_write(*data)
    writes = []
    ref.hook_add(UC_HOOK_MEM_WRITE,
                 lambda _, access, addr, size, value, user: writes.append((addr, size)))
    return ref, writes


def compare_step(cpu, ref, writes):
    pc = cpu.pc
    writes.clear()
    ref.emu_start(pc, MAP_END, count=1)
    entry = cpu.step()
    actual = (cpu.pc, *cpu.registers)
    expected = tuple(ref.reg_read_batch([UC_RISCV_REG_PC, *REG_IDS]))
    if actual != expected:
        diff = [(name, a, e) for name, a, e in zip(["PC"] + [f"x{i}" for i in range(32)], actual, expected) if a != e]
        raise AssertionError(f"{pc:#x}: {entry.instruction}: {diff}")
    mem = entry.mem_write
    if writes != ([(mem[0], len(mem[2]))] if mem else []):
        raise AssertionError(f"{pc:#x}: direcciones de escritura diferentes")
    for addr, width in writes:
        if cpu.memory.read(addr, width) != ref.mem_read(addr, width):
            raise AssertionError(f"{pc:#x}: contenido de memoria diferente en {addr:#x}")
    return entry.instruction.op


def compare_vectors():
    vectors = [(word, a, b, None) for _, word, a, b, _ in ALU]
    vectors += [(i(f3, -4, op=3), 0x104, 0, (0x100, bytes.fromhex("81 fe 34 12"))) for _, f3, _ in LOADS]
    vectors += [(s(f3, -4), 0x104, 0x12345678, (0x100, b"\xab" * 4)) for _, f3, _ in STORES]
    for _, f3, taken, untaken in BRANCHES:
        vectors.extend([(branch(f3, -8), *taken, None), (branch(f3, 8), *untaken, None)])
    vectors += [(0xABCDE2B7, 0, 0, None), (0xFFFFF297, 0, 0, None),
                (jal(-16), 0, 0, None), (i(0, -3, rd=3, op=0x67), 0x184, 0, None)]
    covered = set()
    for word, a, b, data in vectors:
        cpu = CPU()
        code = raw(word)
        cpu.load_image(code)
        cpu.pc = 0x1000
        cpu.memory.write(cpu.pc, code)
        cpu._regs[3:5] = [a, b]
        if data is not None:
            cpu.memory.write(*data)
        ref, writes = reference(cpu, cpu.pc, code, data)
        covered.add(compare_step(cpu, ref, writes))
    if len(covered) != 37:
        raise AssertionError(f"cobertura diferencial incompleta: {covered}")
    print(f"{len(vectors)} vectores; {len(covered)}/37 instrucciones coinciden con Unicorn.")


def main():
    compare_vectors()
    total = 0
    for name, (stop_pc, expected_steps) in EXPECTED_EXAMPLES.items():
        cpu = CPU()
        cpu.load(EXAMPLES / f"{name}.bin")
        ref, writes = reference(cpu, 0, cpu.image)
        for _ in range(expected_steps):
            compare_step(cpu, ref, writes)
        if cpu.pc != stop_pc:
            raise AssertionError(f"{name}: punto final inesperado {cpu.pc:#x}")
        total += expected_steps
        print(f"{name}: {cpu.steps} pasos, PC={cpu.pc:#010x}; PC, 32 registros y escrituras coinciden.")
    print(f"{total} pasos de integración comparados.")


if __name__ == "__main__":
    main()
