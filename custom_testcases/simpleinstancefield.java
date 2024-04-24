public class simpleinstancefield {
  public int field;
  public int lksd;

  public simpleinstancefield() {}
  
  public static int test() {
    simpleinstancefield s = new simpleinstancefield();
    s.lksd = 15;
    return s.lksd;
  }
}
