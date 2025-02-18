from lark.lexer import Token
from colorama import Fore, Style

def missing_arg_error_handler(e):
    print("\t" + f"⚠️ {Fore.YELLOW}Parsing warning:{Style.RESET_ALL} Unexpected token {repr(e.token)} at line {e.line}, column {e.column}. Expected one of: {e.expected}")

    if e.token.type == "_NEWLINE" and e.expected:
        print("\t" + f"⚠️ Injecting missing argument at line {e.line}")

        missing_token_type = next(iter(e.expected))
        e.interactive_parser.feed_token(Token(missing_token_type, "__ERROR__"))
        e.interactive_parser.feed_token(e.token)
        return True

    return False
