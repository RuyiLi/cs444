// JOOS1: PARSER_WEEDER,JOOS1_MULTI_ARRAY,PARSER_EXCEPTION
// JOOS2: TYPE_CHECKING,ASSIGN_TYPE
// JAVAC:UNKNOWN
/**
 * Parser/weeder:
 * - (Joos 1) No multidimensional array creation expressions allowed.
 * - (Joos 2) int[][] is not assignable to int
 */
public class Je_16_MultiArrayCreation_Assign_1{

    public Je_16_MultiArrayCreation_Assign_1(){}
    public static int test() {
	Object a = new Object();
	// a = (Object) (Object)a;
	a = (char)92+"1";
	//int i = (ia[5]) ia;
	int i = (Integer[5]) ia;
	a = (Object)(Object)a;
	// if (s.equals((Object)s2)) return 123;
    }




}