public class loop_array_access {
    public loop_array_access() { }
    public static int test() {
        int[] a = new int[5];
        for (int i = 0; i < a.length - 1; i = i + 1) {
            a[i] = i;
        }
        return a[2];
    }
}

          // for (int j = 0; j < 5; j = j + 1) {
          //   int x = 1;
          // }
          // a = new int[1];
