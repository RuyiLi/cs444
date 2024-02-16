// import foo.A;
// import foo.B;
import foo.bar.baz.B;
import foo.bar.baz.B;
import foo.*;
import foo.bar.*;

public class A {
  public B x;
  public foo.bar.C[] y;
  public C[] z;
  public int[] z1;
  public int z2;

  public A() {
    B b = new B();
    // foo.B b2 = new foo.B();
    foo.bar.baz.B b2 = new foo.bar.baz.B();
    foo.bar.C c = new C();
    int foo = A.B();
    int bar = foo + foo.bar.A.B();
  }
}

// type names to resolve:
// B
// foo.B
// foo.bar.C
// A.B
// C
// foo.bar.A.B
