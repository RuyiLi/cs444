// JOOS1:REACHABILITY,UNREACHABLE_STATEMENT
// JOOS2:REACHABILITY,UNREACHABLE_STATEMENT
// JAVAC:UNKNOWN
// 
/**
 * Reachability:
 * - Check that all statements (including empty statements and empty
 * blocks) are reachable.  
 */
public class control_flow_if_else {

    public control_flow_if_else () {}

    public static int test(int j) {
			if(j == 1) return j + 1;
			else return j - 9;
			int asdf = j;
			if(j == 2) return asdf * j * 22;

			if(j == 1){ 
				j = j + j;
				int x = (j = 9) + 9; 
				return x * j;}

			if (asdf == 2) {
				asdf = 3;
			} else if (asdf == j + 2) {
				j = j - 1;
			}
			else {
				return 3;
			}
			

	if (j == 0) {
	    return 7;
	}
	else {
	    int k = 6;
	    return (j = 2);
	    int l = 9;
	}
	return 123;
    }

}
