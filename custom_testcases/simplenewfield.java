public class simplenewfield {
  public int field = 42;

  public simplenewfield() {}
  
  public static int test() {
    simplenewfield s = new simplenewfield();
    return s.field;
  }
}
