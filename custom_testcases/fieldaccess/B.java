package fieldaccess;

public class B {
    public static int asdf = 100;
    public B() {}
    public static int foo(int a) {
        return 42;
    }
    public static int foo(boolean b) {
        return 43;
    }
}
