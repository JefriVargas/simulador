"""Regenera los .bin con GNU binutils para RISC-V, únicamente para los ejemplos."""

from argparse import ArgumentParser
from pathlib import Path
from subprocess import check_call, check_output
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
ENTRY_AND_STOP = {
    "basico": ("_start", "fin"),
    "riscvtest": ("main", "done"),
    "quicksort": ("_start", "_end"),
    "arbol": ("_start", None),  # Identificar la instrucción «j .» en la entrada.
}


def build(prefix: str, name: str, tmp: Path) -> None:
    entry, stop = ENTRY_AND_STOP[name]
    obj, elf, raw = (tmp / f"{name}.{ext}" for ext in ("o", "elf", "bin"))
    source = tmp / f"{name}.s"
    source.write_bytes((HERE / source.name).read_bytes().rstrip(b"\r\n") + b"\n")
    check_call([prefix + "as", "-march=rv32i", "-mabi=ilp32", "-o", str(obj), str(source)])
    check_call([prefix + "ld", "-m", "elf32lriscv", "--no-relax", "-T", str(HERE / "rv32i.ld"),
                "-e", "0", "-o", str(elf), str(obj)])
    check_call([prefix + "objcopy", "-O", "binary", str(elf), str(raw)])
    image = raw.read_bytes()
    symbols = {}
    for line in check_output([prefix + "nm", str(elf)], text=True).splitlines():
        fields = line.split()
        if len(fields) == 3:
            symbols[fields[2]] = int(fields[0], 16)
    if symbols[entry] != 0:
        raise ValueError(f"{name}: el punto de entrada no quedó en cero")
    if stop is None:
        # jal x0,0 se codifica como 0000006F. Buscarlo anterior a la subrutina.
        stop_pc, = (i for i in range(0, symbols["is_symmetric"], 4)
                    if image[i:i+4] == bytes.fromhex("6F 00 00 00"))
    else:
        stop_pc = symbols[stop]
    (HERE / f"{name}.bin").write_bytes(image)
    print(f"{name}.bin: {len(image)} bytes; PC final = 0x{stop_pc:08X}")


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default="riscv-none-elf-", help="prefijo y ruta opcional de GNU binutils")
    options = parser.parse_args()
    with TemporaryDirectory() as tmpdir:
        for program in ENTRY_AND_STOP:
            build(options.prefix, program, Path(tmpdir))
