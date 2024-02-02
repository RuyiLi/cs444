public class method_similar_signature {
    public method_similar_signature(){}

    public int x(int a, boolean f) {}

    // Extra param
    public int x(int b, boolean g, int c) {}

    // Different id
    public int y(int a, boolean f) {}

    // Different param order
    public int x(boolean f, int a) {}

    public int[] x(int c) {}
}