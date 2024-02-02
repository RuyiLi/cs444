public class void_function_return_expr {
	public void_function_return_expr() {}
	
  // A void function cannot have an expression in a return statement.
	public static void method(int i) {
    return (int)4+5;
  }
}
