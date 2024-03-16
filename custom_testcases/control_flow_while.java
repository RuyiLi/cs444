// JOOS1:REACHABILITY,UNREACHABLE_STATEMENT
// JOOS2:REACHABILITY,UNREACHABLE_STATEMENT
// JAVAC:UNKNOWN
// 
/**
 * Reachability:
 * - Check that all statements (including empty statements and empty
 * blocks) are reachable.  
 */
public class control_flow_while {

    public control_flow_while () {}

    public static int test(int j) {
			while(j > 2) {
        j = j + 1;
        if (j == 123) return j;
      }

      int x = j;
      return x;
    }

}
