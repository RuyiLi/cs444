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
    return a.x + a.y + a.z + a.k;

    // B b = new B();
    // return b.x + b.y + b.z;

    // C c = new C();
    // return c.x + c.y;
  }
}
