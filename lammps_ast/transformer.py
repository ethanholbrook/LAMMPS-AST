from lark import Transformer, Tree

class RemoveNewlines(Transformer):
    def _NEWLINE(self, token):
        return None

    def __default__(self, data, children, meta):
        filtered_children = [child for child in children if child is not None]
        return Tree(data, filtered_children, meta)
