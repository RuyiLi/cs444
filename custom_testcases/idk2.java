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
import local;

public class idk2 extends idk3 {

    public idk2() {}

    public static int test() {
	int j = 0;
	for (int r = 0; r < 42; r = r + 1) {
	    r = r + 1;
	}
	return 123;
    }
}
