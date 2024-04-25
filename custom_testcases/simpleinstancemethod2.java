public class simpleinstancemethod2 {
  public int x = 1;
  public int addOne(int x) {
    return x + 1;
  }

  public simpleinstancemethod2() { this.x = 2; }
  public simpleinstancemethod2(int x) { this.x = x; }

  public static int test() {
    simpleinstancemethod2 s = new simpleinstancemethod2(3);
    // simpleinstancemethod s = new simpleinstancemethod();
    return s.addOne(s.x);
    // return s.x;
  }
}
