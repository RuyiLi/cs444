CC = gcc
LEX = flex
YACC = bison

joosc:
	$(CC) -o $@ -lfl

# joosc.lex.yy.c: joosc.l
# 	$(LEX) -o $@ $^

# joosc.tab.c: joosc.y
# 	$(YACC) -d -o $@ $^

.PHONY: clean
clean:
	rm -f joosc 
# joosc.lex.yy.c joosc.tab.c joosc.tab.h