package whatever.asdf;

import fieldaccess.B;

public class A {
    public A() {}
    
    public static int test() {
        int res = fieldaccess.B.foo(1) + B.foo(true);
        return fieldaccess.B.asdf + res + A.foo();
    }

    public static int foo() {
        return -42;
    }
}
