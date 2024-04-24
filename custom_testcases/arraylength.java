public class arraylength {
    public arraylength() {}
    public static int test() {
      int[] r = new int[7];
      int x = r.length;
      return x + arraylength.arrLength(r);
    }

    public static int arrLength(int[] arr) {
      int i = arr.length;
      return i;
    }
}
