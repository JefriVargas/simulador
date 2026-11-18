"""RAM plana de 32 bits. Los bloques internos solo ahorran memoria del host."""

SIZE = 1 << 32
PAGE = 4096
ZERO_PAGE = bytes(PAGE)


class MemoryFault(ValueError):
    pass


class Memory:
    def __init__(self) -> None:
        self._pages: dict[int, bytearray] = {}

    @staticmethod
    def check_span(addr: int, length: int) -> None:
        if not (0 <= addr < SIZE and 0 <= length <= SIZE - addr):
            raise MemoryFault(f"rango fuera de 32 bits: {addr:#x} + {length} bytes")

    def read(self, addr: int, length: int) -> bytes:
        self.check_span(addr, length)
        result = bytearray()
        while length:
            page, offset = divmod(addr, PAGE)
            count = min(length, PAGE - offset)
            result.extend(self._pages.get(page, ZERO_PAGE)[offset:offset + count])
            addr += count
            length -= count
        return bytes(result)

    def write(self, addr: int, data: bytes) -> None:
        self.check_span(addr, len(data))
        done = 0
        while done < len(data):
            page, offset = divmod(addr + done, PAGE)
            count = min(len(data) - done, PAGE - offset)
            block = data[done:done + count]
            target = self._pages.get(page)
            if target is not None or any(block):
                if target is None:
                    target = self._pages[page] = bytearray(PAGE)
                target[offset:offset + count] = block
            done += count

    def read_int(self, addr: int, width: int) -> int:
        return int.from_bytes(self.read(addr, width), "little")
