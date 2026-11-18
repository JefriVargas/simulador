/* Binario bare metal: byte 0 del archivo = dirección 0 de la RAM. */
SECTIONS
{
    . = 0;
    .text : { *(.text .text.*) }
    .rodata : { *(.rodata .rodata.*) }
    .data : { *(.data .data.*) }
    .bss (NOLOAD) : { *(.bss .bss.*) *(COMMON) }
    /DISCARD/ : { *(.riscv.attributes) *(.comment) }
}
