public class nested_class {
    public nested_class() {}

    // Cannot contain nested types
    public class nested_class {
        public nested_class() {}
    }
}
