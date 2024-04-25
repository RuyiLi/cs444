public class simpleinstancemethod {
  public simpleinstancemethod() {}

  public int getLKSD() {
    return 4;
  }
  
  public static int test() {
    simpleinstancemethod s = new simpleinstancemethod();
    return s.getLKSD();
  }
}
