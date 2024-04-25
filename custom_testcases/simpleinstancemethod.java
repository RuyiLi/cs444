public class simpleinstancemethod {
  public int x = 1;
  public int addOne(int x) {
    return x + 1;
  }

  public simpleinstancemethod() { this.x = 2; }
  public simpleinstancemethod(int x) { this.x = x; }

  public static int test() {
    simpleinstancemethod s = new simpleinstancemethod(3);
    // simpleinstancemethod s = new simpleinstancemethod();
    // return s.addOne(s.x);
    return s.x;
  }
}
