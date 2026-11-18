"""Interfaz de terminal para cargar, ejecutar e inspeccionar programas."""

import argparse
from pathlib import Path
from typing import TextIO

from .cpu import CPU, DEFAULT_SP
from .isa import sx
from .memory import Memory, SIZE

ABI = (
    "zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2",
    "s0", "s1", "a0", "a1", "a2", "a3", "a4", "a5",
    "a6", "a7", "s2", "s3", "s4", "s5", "s6", "s7",
    "s8", "s9", "s10", "s11", "t3", "t4", "t5", "t6",
)
BY_NAME = {name: i for i, name in enumerate(ABI)} | {"fp": 8}
BY_NAME.update({f"x{i}": i for i in range(32)})
RUN_LIMIT = 1_000_000
HELP = """Comandos:
  load ARCHIVO                Carga un binario raw desde 0x00000000.
  step                        Ejecuta una instrucción y muestra sus efectos.
  pc                          Muestra la dirección de la siguiente instrucción.
  regs [xN|alias ...]          Muestra registros elegidos, o los 32.
  mem INICIO FIN              Muestra bytes; los dos extremos son inclusivos.
  words INICIO CANTIDAD       Muestra palabras de 32 bits en hex y decimal con signo.
  run LÍMITE [HASTA_PC]        Ejecuta como máximo LÍMITE pasos (hasta 1 000 000);
                              si se indica HASTA_PC, para antes de ejecutarlo.
  reset                       Restaura el binario original, PC y registros.
  help                        Muestra los comandos.
  exit                        Cierra el simulador.
  Los números admiten decimal o hexadecimal con prefijo 0x."""


def number(token: str) -> int:
    return int(token, 16 if token.lower().startswith("0x") else 10)


def arity(args: list[str], count: int, usage: str) -> None:
    if len(args) != count:
        raise ValueError(f"uso: {usage}")


def show_step(cpu: CPU) -> None:
    step = cpu.step()
    print(f"0x{step.pc:08X}  {step.word:08X}  {step.instruction}  ->  PC=0x{step.next_pc:08X}")
    if step.reg_write:
        i, before, after = step.reg_write
        print(f"  x{i} ({ABI[i]}): 0x{before:08X} -> 0x{after:08X}")
    if step.mem_write:
        addr, before, after = step.mem_write
        print(f"  mem[0x{addr:08X}]: {before.hex(' ').upper()} -> {after.hex(' ').upper()}")


def run(cpu: CPU, limit: int, stop: int | None) -> None:
    if not 1 <= limit <= RUN_LIMIT:
        raise ValueError(f"el límite debe estar entre 1 y {RUN_LIMIT}")
    if stop is not None and not (0 <= stop < SIZE and stop % 4 == 0):
        raise ValueError("el PC de parada debe ser de 32 bits y múltiplo de 4")
    start = cpu.steps
    while cpu.steps - start < limit and cpu.pc != stop:
        cpu.step()
    reason = "PC objetivo alcanzado" if cpu.pc == stop else "límite de pasos alcanzado"
    print(f"{reason}: {cpu.steps - start} instrucciones; PC=0x{cpu.pc:08X}")


def execute(cpu: CPU, line: str) -> bool:
    """Devuelve False solo si se solicitó cerrar la sesión."""
    parts = line.split(maxsplit=1)
    if not parts or parts[0].startswith("#"):
        return True
    cmd = parts[0].lower()
    tail = parts[1] if len(parts) == 2 else ""
    args = tail.split()
    match cmd:
        case "load":
            if len(tail) >= 2 and tail[0] == tail[-1] and tail[0] in "\"'":
                tail = tail[1:-1]
            if not tail:
                raise ValueError("uso: load ARCHIVO")
            print(f"{Path(tail).name}: {cpu.load(tail)} bytes cargados desde 0x00000000.")
        case "step":
            arity(args, 0, "step")
            show_step(cpu)
        case "pc":
            arity(args, 0, "pc")
            print(f"PC = 0x{cpu.pc:08X}  |  pasos = {cpu.steps}")
        case "regs":
            try:
                indices = [BY_NAME[arg.lower()] for arg in args] if args else range(32)
            except KeyError as exc:
                raise ValueError(f"registro desconocido: {exc.args[0]}") from exc
            values = cpu.registers
            for i in indices:
                print(f"x{i:<2} ({ABI[i]:>4}) = 0x{values[i]:08X}  ({sx(values[i], 32)})")
        case "mem":
            arity(args, 2, "mem INICIO FIN")
            start, end = map(number, args)
            count = end - start + 1
            if not 1 <= count <= 4096:
                raise ValueError("el rango inclusivo debe contener entre 1 y 4096 bytes")
            data = cpu.memory.read(start, count)
            for i in range(0, count, 16):
                print(f"0x{start+i:08X}: {data[i:i+16].hex(' ').upper()}")
        case "words":
            arity(args, 2, "words INICIO CANTIDAD")
            start, count = map(number, args)
            if start % 4 or not 1 <= count <= 256:
                raise ValueError("se requiere dirección múltiplo de 4 y cantidad entre 1 y 256")
            Memory.check_span(start, count * 4)
            for addr in range(start, start + count * 4, 4):
                word = cpu.memory.read_int(addr, 4)
                print(f"0x{addr:08X}: 0x{word:08X}  ({sx(word, 32)})")
        case "run":
            if not 1 <= len(args) <= 2:
                raise ValueError("uso: run LÍMITE [HASTA_PC]")
            run(cpu, number(args[0]), number(args[1]) if len(args) == 2 else None)
        case "reset":
            arity(args, 0, "reset")
            cpu.reset()
            print("Estado inicial restaurado.")
        case "help" | "h":
            arity(args, 0, "help")
            print(HELP)
        case "exit" | "quit":
            arity(args, 0, "exit")
            return False
        case _:
            raise ValueError(f"comando desconocido: {cmd}. Escribe help.")
    return True


def session(cpu: CPU, script: TextIO | None = None) -> int:
    while True:
        try:
            if script is None:
                line = input("rv32i> ").strip()
            else:
                record = script.readline()
                if not record:
                    return 0
                line = record.strip()
                if not line or line.startswith("#"):
                    continue
                print(f"rv32i> {line}")
            if not execute(cpu, line):
                return 0
        except EOFError:
            return 0
        except (OSError, ValueError) as exc:
            print(f"Error: {exc}")
            if script is not None:
                return 1
        except KeyboardInterrupt:
            print("\nInterrumpido.")
            return 130


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulador funcional RV32I — CS3051")
    parser.add_argument("programa", nargs="?", help="archivo binario raw")
    parser.add_argument("--sp", type=number, default=DEFAULT_SP, help="puntero de pila inicial")
    parser.add_argument("--script", type=Path, help="ejecuta comandos de un archivo UTF-8")
    args = parser.parse_args()
    try:
        cpu = CPU(args.sp)
        if args.programa:
            size = cpu.load(args.programa)
            print(f"{Path(args.programa).name}: {size} bytes cargados desde 0x00000000.")
        if args.script:
            with args.script.open(encoding="utf-8-sig") as commands:
                return session(cpu, commands)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    print("RV32I | Escribe help para ver los comandos.")
    return session(cpu)


if __name__ == "__main__":
    raise SystemExit(main())
