public class method_same_signature {
    public method_same_signature(){}

    public static int x(int[] a, boolean f) {}

    // Two methods cannot have the same signature.
    public boolean x(int[] b, boolean g) {}

    public int[] x(int c) {}
}