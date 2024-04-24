public class A extends B {
  public int k = 4;
  public A() {
    // int k = 3;
    k = 9;
    // int k = 3;
  }
  public static int test() {
    A a = new A();
    // a.k = a.k - 3;
    return a.k;
  }
}
