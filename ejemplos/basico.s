    .text
    .globl _start
_start:
    addi x5, x0, 5
    addi x6, x0, 7
    add  x7, x5, x6
    sw   x7, 100(x0)
    lw   x8, 100(x0)
fin:
    jal  x0, fin
