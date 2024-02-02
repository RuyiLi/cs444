public class minus_cast_minus {
    public minus_cast_minus() {}

    public int A() {
        int x = 4;
        // y is assigned the value of 4 (not 3)
        int y = -(int)-x;
    }
}
