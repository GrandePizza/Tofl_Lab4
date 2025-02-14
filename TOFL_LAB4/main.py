class RegexParserError(Exception):
    pass


class Token:
    def __init__(self, ttype, value=None):
        self.ttype = ttype
        self.value = value

    def __repr__(self):
        return f"Token({self.ttype}, {self.value})"


class Lexer:
    def __init__(self, text):
        self.text = text
        self.pos = 0

    def peek(self):
        if self.pos < len(self.text):
            return self.text[self.pos]
        return None

    def tokenize(self):
        tokens = []
        while self.pos < len(self.text):
            char = self.peek()

            if char == '(':
                self.pos += 1
                next_char = self.peek()
                if next_char == '?':
                    self.pos += 1
                    next_char_2 = self.peek()
                    if next_char_2 == ':':
                        self.pos += 1
                        tokens.append(Token('NONCAP_OPEN'))
                    elif next_char_2 == '=':
                        # (?= )
                        self.pos += 1
                        tokens.append(Token('LOOKAHEAD_OPEN'))
                    elif next_char_2 and next_char_2.isdigit():
                        # (?N)
                        self.pos += 1
                        val = int(next_char_2)
                        tokens.append(Token('EXPR_REF_OPEN', val))
                    else:
                        raise RegexParserError()
                else:
                    tokens.append(Token('CAP_OPEN'))
            elif char == ')':
                tokens.append(Token('CLOSE'))
                self.pos += 1
            elif char == '|':
                tokens.append(Token('ALT'))
                self.pos += 1
            elif char == '*':
                tokens.append(Token('STAR'))
                self.pos += 1
            elif char and 'a' <= char <= 'z':
                tokens.append(Token('CHAR', char))
                self.pos += 1
            else:
                raise RegexParserError()
        return tokens


# Узлы AST
class GroupNode:
    def __init__(self, group_id, node):
        self.group_id = group_id
        self.node = node

    def __repr__(self):
        return f"GroupNode({self.group_id}, {self.node})"


class NonCapGroupNode:
    def __init__(self, node):
        self.node = node

    def __repr__(self):
        return f"NonCapGroupNode({self.node})"


class LookaheadNode:
    def __init__(self, node):
        self.node = node

    def __repr__(self):
        return f"LookaheadNode({self.node})"


class ConcatNode:
    def __init__(self, nodes):
        self.nodes = nodes

    def __repr__(self):
        return f"ConcatNode({self.nodes})"


class AltNode:
    def __init__(self, branches):
        self.branches = branches

    def __repr__(self):
        return f"AltNode({self.branches})"


class StarNode:
    def __init__(self, node):
        self.node = node

    def __repr__(self):
        return f"StarNode({self.node})"


class CharNode:
    def __init__(self, ch):
        self.ch = ch

    def __repr__(self):
        return f"CharNode('{self.ch}')"


class ExprRefNode:
    def __init__(self, ref_id):
        self.ref_id = ref_id

    def __repr__(self):
        return f"ExprRefNode({self.ref_id})"


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.group_count = 0
        self.in_lookahead = False

        self.groups_ast = {}

    def current_token(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def read(self, ttype=None):
        tok = self.current_token()
        if tok is None:
            raise RegexParserError()
        if ttype is not None and tok.ttype != ttype:
            raise RegexParserError()
        self.pos += 1
        return tok

    def parse(self):
        node = self.parse_alternation()
        if self.current_token() is not None:
            raise RegexParserError()

        all_groups = self.collect_all_groups(node, set())

        self.check_references(node, all_groups)

        return node

    def collect_all_groups(self, node, defined_groups):
        if isinstance(node, GroupNode):
            defined_groups.add(node.group_id)
            self.collect_all_groups(node.node, defined_groups)
            return defined_groups

        if isinstance(node, NonCapGroupNode):
            return self.collect_all_groups(node.node, defined_groups)

        if isinstance(node, LookaheadNode):
            return self.collect_all_groups(node.node, defined_groups)

        if isinstance(node, StarNode):
            return self.collect_all_groups(node.node, defined_groups)

        if isinstance(node, ConcatNode):
            for child in node.nodes:
                self.collect_all_groups(child, defined_groups)
            return defined_groups

        if isinstance(node, AltNode):
            for branch in node.branches:
                self.collect_all_groups(branch, defined_groups)
            return defined_groups

        if isinstance(node, CharNode):
            return defined_groups

        if isinstance(node, ExprRefNode):
            return defined_groups

        raise RegexParserError()

    def parse_alternation(self):
        # alternation: concatenation ('|' concatenation)*
        branches = [self.parse_concatenation()]
        while self.current_token() and self.current_token().ttype == 'ALT':
            self.read('ALT')
            if self.current_token() is None or self.current_token().ttype in ['CLOSE', 'ALT']:
                raise RegexParserError()
            branches.append(self.parse_concatenation())
        if len(branches) == 1:
            return branches[0]
        return AltNode(branches)

    def parse_concatenation(self):
        nodes = []
        while self.current_token() and self.current_token().ttype not in ['CLOSE', 'ALT']:
            nodes.append(self.parse_repetition())
        if len(nodes) == 1:
            return nodes[0]
        return ConcatNode(nodes)

    def parse_repetition(self):
        node = self.parse_base()
        while self.current_token() and self.current_token().ttype == 'STAR':
            self.read('STAR')
            node = StarNode(node)
        return node

    def parse_base(self):
        tok = self.current_token()
        if tok is None:
            raise RegexParserError()

        if tok.ttype == 'CAP_OPEN':
            self.read('CAP_OPEN')
            self.group_count += 1
            if self.group_count > 9:
                raise RegexParserError()
            group_id = self.group_count
            node = self.parse_alternation()
            self.read('CLOSE')
            self.groups_ast[group_id] = node
            return GroupNode(group_id, node)

        elif tok.ttype == 'NONCAP_OPEN':
            self.read('NONCAP_OPEN')
            node = self.parse_alternation()
            self.read('CLOSE')
            return NonCapGroupNode(node)

        elif tok.ttype == 'LOOKAHEAD_OPEN':
            if self.in_lookahead:
                raise RegexParserError()
            self.read('LOOKAHEAD_OPEN')
            old_look = self.in_lookahead
            self.in_lookahead = True
            node = self.parse_alternation()
            self.in_lookahead = old_look
            self.read('CLOSE')
            return LookaheadNode(node)

        elif tok.ttype == 'EXPR_REF_OPEN':
            ref_id = tok.value
            self.read('EXPR_REF_OPEN')
            self.read('CLOSE')
            return ExprRefNode(ref_id)

        elif tok.ttype == 'CHAR':
            ch = tok.value
            self.read('CHAR')
            return CharNode(ch)

        else:
            raise RegexParserError()

    def check_references(self, node, all_groups):
        if isinstance(node, ExprRefNode):
            if node.ref_id not in all_groups:
                raise RegexParserError()
            return

        if isinstance(node, GroupNode):
            self.check_references(node.node, all_groups)
            return

        if isinstance(node, NonCapGroupNode):
            self.check_references(node.node, all_groups)
            return

        if isinstance(node, LookaheadNode):
            self.check_no_cap_and_lookahead(node.node, inside_lookahead=True)
            self.check_references(node.node, all_groups)
            return

        if isinstance(node, StarNode):
            self.check_references(node.node, all_groups)
            return

        if isinstance(node, ConcatNode):
            for child in node.nodes:
                self.check_references(child, all_groups)
            return

        if isinstance(node, AltNode):
            for branch in node.branches:
                self.check_references(branch, all_groups)
            return

        if isinstance(node, CharNode):
            return

        raise RegexParserError()

    def check_no_cap_and_lookahead(self, node, inside_lookahead):

        if isinstance(node, GroupNode) and inside_lookahead:
            raise RegexParserError()
        if isinstance(node, LookaheadNode) and inside_lookahead:
            raise RegexParserError()

        if isinstance(node, (NonCapGroupNode, LookaheadNode, StarNode, ConcatNode, AltNode)):
            children = node.nodes if hasattr(node, "nodes") else [node.node]
            for child in children:
                self.check_no_cap_and_lookahead(child, inside_lookahead)


class CFGBuilder:
    def __init__(self, groups_ast):
        # groups_ast: {group_id: node}
        self.groups_ast = groups_ast
        self.group_nonterm = {}
        self.noncap_index = 1
        self.star_index = 1

    def build(self, node):
        start = 'S'
        rules = {}

        main_nt = self.node_to_cfg(node, rules)

        rules[start] = [[main_nt]]

        for group_id, ast in self.groups_ast.items():
            if group_id not in self.group_nonterm:
                nt = f"G{group_id}"
                self.group_nonterm[group_id] = nt
                self.node_to_cfg(ast, rules, start_symbol=nt)

        return start, rules

    def node_to_cfg(self, node, rules, start_symbol=None):
        if isinstance(node, CharNode):
            nt = start_symbol if start_symbol else self.fresh_nt('CHAR')
            rules.setdefault(nt, []).append([node.ch])
            return nt

        elif isinstance(node, GroupNode):
            nt = self.group_nonterm.get(node.group_id)
            if nt is None:
                nt = f"G{node.group_id}"
                self.group_nonterm[node.group_id] = nt
            sub_nt = self.node_to_cfg(node.node, rules)
            rules.setdefault(nt, []).append([sub_nt])
            return nt

        elif isinstance(node, NonCapGroupNode):
            nt = start_symbol if start_symbol else self.fresh_nt('N')
            sub_nt = self.node_to_cfg(node.node, rules)
            rules.setdefault(nt, []).append([sub_nt])
            return nt

        elif isinstance(node, LookaheadNode):
            nt = start_symbol if start_symbol else self.fresh_nt('LA')
            rules.setdefault(nt, []).append([])
            return nt

        elif isinstance(node, ConcatNode):
            nt = start_symbol if start_symbol else self.fresh_nt('C')
            seq_nts = [self.node_to_cfg(ch, rules) for ch in node.nodes]
            rules.setdefault(nt, []).append(seq_nts)
            return nt

        elif isinstance(node, AltNode):
            nt = start_symbol if start_symbol else self.fresh_nt('A')
            for branch in node.branches:
                br_nt = self.node_to_cfg(branch, rules)
                rules.setdefault(nt, []).append([br_nt])
            return nt

        elif isinstance(node, StarNode):
            nt = start_symbol if start_symbol else self.fresh_nt('R')
            sub_nt = self.node_to_cfg(node.node, rules)
            rules.setdefault(nt, []).append([])
            rules[nt].append([nt, sub_nt])
            return nt

        elif isinstance(node, ExprRefNode):
            # Ссылка на выражение группы
            ref_id = node.ref_id
            if ref_id not in self.group_nonterm:
                self.group_nonterm[ref_id] = f"G{ref_id}"
                if ref_id not in self.groups_ast:
                    raise RegexParserError()
                sub_nt = self.node_to_cfg(self.groups_ast[ref_id], rules)
                nt = self.group_nonterm[ref_id]
                rules.setdefault(nt, []).append([sub_nt])
            return self.group_nonterm[ref_id]

        else:
            raise RegexParserError()

    def fresh_nt(self, prefix):
        if prefix == 'N':
            name = f"N{self.noncap_index}"
            self.noncap_index += 1
            return name
        elif prefix == 'R':
            name = f"R{self.star_index}"
            self.star_index += 1
            return name
        else:
            name = f"{prefix}{self.noncap_index + self.star_index}"
            self.noncap_index += 1
            return name


def main():
    text = input().strip()
    try:
        if text == "":
            raise RegexParserError()
        lexer = Lexer(text)
        tokens = lexer.tokenize()

        parser = Parser(tokens)
        ast = parser.parse()

        builder = CFGBuilder(parser.groups_ast)
        start_symbol, rules = builder.build(ast)
        print("OK.")
        for nt in rules:
            for rhs in rules[nt]:
                rhs_str = " ".join(rhs) if rhs else "ε"
                print(f"{nt} -> {rhs_str}")

    except RegexParserError as e:
        print("Ошибка", e)


if __name__ == "__main__":
    main()
