import unittest

from scadfem import tags


class ParseTest(unittest.TestCase):
    def test_module_tags(self):
        src = '''
//@sim material=steel name=a
module beam(l = 3) { cube(l); }
// other comment
//@sim fixed
module wall() cube([1, 2, 3]);
//@sim load force=[0,5,-1]
module tip() cube(1);
'''
        a, b, c = tags.parse(src)
        self.assertEqual((a.kind, a.args["material"], a.module, a.name), ("part", "steel", "beam", "a"))
        self.assertEqual((b.kind, b.module, b.name), ("fixed", "wall", "fixed"))
        self.assertEqual(c.args["force"], [0, 5, -1])

    def test_no_module_tags(self):
        t, = tags.parse("//@sim contact a b mode=tie\ncube(1);")
        self.assertEqual((t.kind, t.words, t.module), ("contact", ["a", "b"], ""))

    def test_statement_rejected(self):
        with self.assertRaises(tags.TagError):
            tags.parse("//@sim material=steel\ncube(1);")

    def test_two_tags_in_a_row_rejected(self):
        with self.assertRaises(tags.TagError):
            tags.parse("//@sim material=steel\n//@sim fixed\nmodule m() cube(1);")


if __name__ == "__main__":
    unittest.main()
