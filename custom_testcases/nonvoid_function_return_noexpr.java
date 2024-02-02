public class nonvoid_function_return_noexpr {
	public nonvoid_function_return_noexpr() {}
	
  // A non-void function must have an expression in a return statement.
	public static int method(int i) {
    return;
  }
}
