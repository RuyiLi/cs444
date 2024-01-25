from lark import Lark

l = Lark('''
            ?literal: integer_l
            | boolean_l
            # | char_l
            # | string_l
            # | null_l
         
            integer_l: /[0-9]+/

            boolean_l: "true" -> true
            | "false"         -> false

            # char_l: "'" (LETTER+ | escape_seq) "'"
         
            # escape_seq: "\\" (/[btnfr]/ | "\"" | "'" | "\\")

            op: "+"  -> plus
            | "-"    -> minus
            | "*"    -> times
            | "/"    -> divide

            ?expr: literal
            | literal op expr

            %import common.NUMBER
            %import common.LETTER
            %ignore " "           // Disregard spaces in text
         ''', start="expr", parser="lalr")

print(l.parse("true + 3").pretty())