// JOOS1:REACHABILITY,UNREACHABLE_STATEMENT
// JOOS2:REACHABILITY,UNREACHABLE_STATEMENT
// JAVAC:UNKNOWN
// 
/**
 * Reachability:
 * - Check that all statements (including empty statements and empty
 * blocks) are reachable.  
 */
public class control_flow_for {

    public control_flow_for () {}

    public static int test(int j) {
			for (int i = 0; i < j; i = i + i) {
        j = j + 1;
        if (j == 123) return i;
      }

      int x = j;
			for (; x > 0; x = x - 2) {
        int adsf = x * x;
        j = j * x;
      }

      for (x = 0; j < 10; x = j + 1) {
        j = j + 1;
      }
    }

}
