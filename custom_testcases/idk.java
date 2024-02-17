// JOOS1:ENVIRONMENTS,DUPLICATE_VARIABLE
// JOOS2:ENVIRONMENTS,DUPLICATE_VARIABLE
// JAVAC:UNKNOWN
// 
/**
 * Environments:
 * - Check that no two local variables with overlapping scope have the
 * same name.
 */
import java.util.*;


public class idk {

    public idk() {}
    public int m1(int x) {
        return 42;
      }
    public int m1(boolean x) {
        return 87;
      }
    public static int test() {
	int j = 0;
	for (int r = 0; r < 42; r = r + 1) {
	    r = r + 1;
	}
	return 123;
    }
}
