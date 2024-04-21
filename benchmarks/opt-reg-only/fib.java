public class Fib {
    public static void main(String[] args) {
        int n = 10;
        int first = 0;
        int second = 1;
        int fib = 0;
        // System.out.print("Fibonacci Series: ");
        for (int i = 1; i <= n; ++i) {
            System.out.print(first + " ");
            fib = first + second;
            first = second;
            second = fib;
        }
    }
}
