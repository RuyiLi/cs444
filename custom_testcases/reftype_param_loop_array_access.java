public class reftype_param_loop_array_access {
    public reftype_param_loop_array_access() { }
    public static void funny(int[] a) {
      a[0] = 2;
      // for (int i = 0; i < 4; i = i + 1) {
      // }
      // return a.length;
    }
    public static int test() {
        int[] a = new int[5];
        reftype_param_loop_array_access.funny(a);

        // int x = reftype_param_loop_array_access.funny(a);
        // a[0] = x;

        // below returns wrong value??
        // a[0] = reftype_param_loop_array_access.funny(a);

        return 1;
    }
}

