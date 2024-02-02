public class pre_decrement {
    public pre_decrement() {}

    public int A() {
        int x = 4;
        // ERROR: Pre-decrement operator not allowed
        int y = --x;
    }
}
