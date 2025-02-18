from lark import Transformer, Tree
from colorama import Fore, Style

class RemoveNewlinesAndUnsupported(Transformer):
    def _NEWLINE(self, token):
        return None

    def UNSUPPORTED_KEYWORD(self, token):
        print("\t" + f"⚠️ {Fore.YELLOW}Warning:{Style.RESET_ALL} Unsupported keyword '{token.value}' encountered.")
        return token 

    def UNSUPPORTED_ARGS(self, token):
        print("\t" + f"⚠️ {Fore.YELLOW}Warning:{Style.RESET_ALL} Unsupported arguments '{token.value}' encountered.")
        return token 

    def __default__(self, data, children, meta):
        filtered_children = [child for child in children if child is not None]
        return Tree(data, filtered_children, meta)
