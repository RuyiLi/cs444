public class MatrixMult {
    public static void main(String[] args) {
        int[][] firstMatrix = { {1, 2, 3}, {4, 5, 6}, {7, 8, 9} };
        int[][] secondMatrix = { {9, 8, 7}, {6, 5, 4}, {3, 2, 1} };

        int[][] result = new int[firstMatrix.length][secondMatrix[0].length];

        for (int i = 0; i < firstMatrix.length; i++) {
            for (int j = 0; j < secondMatrix[0].length; j++) {
                for (int k = 0; k < firstMatrix[0].length; k++) {
                    result[i][j] += firstMatrix[i][k] * secondMatrix[k][j];
                }
            }
        }

        // System.out.println("Resultant Matrix:");
        for (int i = 0; i < firstMatrix.length; i++) {
            for (int j = 0; j < secondMatrix[0].length; j++) {
                // System.out.print(result[i][j] + " ");
            }
            System.out.println();
        }
    }
}
