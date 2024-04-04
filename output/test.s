global _start
_start:
	mov eax, 10
	; mov ebp, esp
	push eax
	push 101
	push 2
	mov edx, ebp
	sub edx, esp
	mov edx, ebp
	mov eax, 1
	mov ebx, edx
	int 0x80
