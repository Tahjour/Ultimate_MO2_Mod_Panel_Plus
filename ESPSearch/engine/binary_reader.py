import struct


class ByteReader:
    """Последовательный читатель бинарных данных с проверкой границ.

    Этот класс играет ту же роль, что и низкоуровневые ридеры в xEdit
    (реализация чтения из потока байт в wbImplementation.pas):
    аккуратное чтение little-endian значений с проверкой на выход за границы.
    """

    __slots__ = ("data", "pos", "length")

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0
        self.length = len(data)

    @property
    def remaining(self) -> int:
        """Количество байт, оставшихся для чтения."""

        return self.length - self.pos

    def can_read(self, size: int) -> bool:
        """Проверяет, достаточно ли данных для чтения size байт."""

        return self.pos + size <= self.length

    def read(self, size: int) -> bytes:
        """Читает ровно size байт или выбрасывает исключение при нехватке данных."""

        if not self.can_read(size):
            raise ValueError(
                f"Unexpected end of data: need {size} bytes at offset {self.pos}, "
                f"but only {self.remaining} available",
            )
        chunk = self.data[self.pos : self.pos + size]
        self.pos += size
        return chunk

    def peek(self, size: int) -> bytes:
        """Читает данные без продвижения позиции."""

        if not self.can_read(size):
            return b""
        return self.data[self.pos : self.pos + size]

    def skip(self, size: int) -> None:
        """Пропускает size байт или выбрасывает исключение при нехватке данных."""

        if not self.can_read(size):
            raise ValueError(f"Cannot skip {size} bytes at offset {self.pos}")
        self.pos += size

    def read_u8(self) -> int:
        """Читает беззнаковый 8-битный целый (UInt8)."""

        return self._read_struct("<B", 1)

    def read_u16(self) -> int:
        """Читает беззнаковый 16-битный целый (UInt16)."""

        return self._read_struct("<H", 2)

    def read_u32(self) -> int:
        """Читает беззнаковый 32-битный целый (UInt32)."""

        return self._read_struct("<I", 4)

    def read_i32(self) -> int:
        """Читает знаковый 32-битный целый (Int32)."""

        return self._read_struct("<i", 4)

    def read_f32(self) -> float:
        """Читает 32-битный float (Float32)."""

        return self._read_struct("<f", 4)

    def _read_struct(self, fmt: str, size: int):
        """Общий helper для чтения значения через struct.unpack_from.

        В xEdit аналогичная логика разбросана по функциям wbReadInteger,
        wbReadFloat и т.п., которые всегда проверяют наличие достаточного
        количества байт перед чтением.
        """

        if not self.can_read(size):
            raise ValueError(
                f"Cannot read {size} bytes at offset {self.pos}, "
                f"only {self.remaining} remaining",
            )
        value = struct.unpack_from(fmt, self.data, self.pos)[0]
        self.pos += size
        return value

