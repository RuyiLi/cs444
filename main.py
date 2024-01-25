from lark import Lark

l = Lark(
    """
            ?literal:  integer_l
                     | boolean_l
                     | char_l
                     | string_l
                     | null_l
         
            integer_l: INT

            boolean_l: "true"    -> true
                     | "false"   -> false

            char_l: "'" (LETTER | escape_seq) "'"
            escape_seq: "\\\\" (/[btnfr\\\"\\\'\\\\]/ | INT)
         
            string_l: "\\\"" (LETTER | escape_seq)* "\\\""
         
            null_l: "null"

            op:  "+"    -> plus
               | "-"    -> minus
               | "*"    -> times
               | "/"    -> divide

            ?expr:  literal
                  | literal op expr

            %import common.INT
            %import common.LETTER
            %ignore " "           // Disregard spaces in text
         """,
    start="expr",
    parser="lalr"
)

print(l.parse("'f' + 3 - '\\b' / '\\0177' + \"foo\\b\" + null").pretty())
