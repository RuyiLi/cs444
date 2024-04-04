#!/bin/bash

for filename in *.s; do
    nasm -O1 -f elf -g -F dwarf "$filename"
done

ld -melf_i386 -o main *.o

./main; echo $?
