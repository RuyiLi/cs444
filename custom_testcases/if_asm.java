public class if_asm {
    public if_asm() {}
    public static int test() {
      int r = 12;
      int x = if_asm.addTen(r);

      if (!(x < 0)) r = 0;
      // if (x >= 0) r = 0;
      return r + x;
    }

    public static int addTen(int a) {
      return a + 10;
    }
}
