# Tarea 5 · Simulador de RISC-V

Para esta tarea usé Python. El simulador carga archivos `.bin` desde la dirección cero y ejecuta las 37 instrucciones del anexo A. Se puede avanzar una instrucción a la vez y revisar el PC, los registros y la memoria.

## Cómo probarlo

Extraiga el ZIP y abra una terminal en la carpeta `Simulador`. Se necesita Python 3.10 o posterior.

```powershell
python -m rv32i ejemplos/basico.bin
```

Cuando aparezca `rv32i>`, escriba estos comandos uno por uno.

```text
pc
step
regs x5
run 20 0x14
mem 0x64 0x67
exit
```

Con `step` se ejecuta la primera instrucción y `x5` queda en 5. Luego `run 20 0x14` continúa hasta el PC indicado. La consulta de memoria muestra `0C 00 00 00`, que representa el número 12.

## Los cuatro ejemplos

Desde la misma carpeta, este comando ejecuta la demostración completa.

```powershell
python -m rv32i --script ejemplos/demo.txt
```

- **Básico.** Escribe 12 en la dirección `0x64` y lo recupera en `x8`.
- **riscvtest.** Deja 25 en la dirección `0x64`.
- **Quicksort.** Ordena el arreglo en `0x1000`. El resultado es `[1, 2, 3, 4, 6, 8, 9]`.
- **Árbol simétrico.** Devuelve 1 en el registro `a0`.

Para correr las pruebas automáticas, ejecute `python -m unittest -v`. Los binarios ya están incluidos. Para volver a generarlos desde los archivos `.s`, use `python ejemplos/reconstruir.py` con las herramientas GNU para RISC-V disponibles en la terminal.

Se usaron las fuentes indicadas en el enunciado para [riscvtest.s](https://pastebin.com/pKuqWTLh), [quicksort](https://pastebin.com/MmQzpFyR) y [árbol simétrico](https://pastebin.com/R74Uqc68).
