public class loop_array_access {
    public loop_array_access() { }
    public static int test() {
        int[] a = new int[1];
        for (int i = 0; i < 5; i = i + 1) {
          a[0] = 1;
        }
        return 1;
    }

}
