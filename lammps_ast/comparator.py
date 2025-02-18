from zss import simple_distance, Node
from lark.lexer import Token
from collections import defaultdict
from .parser import parse_to_AST

def lark_tree_to_zss(ttree):
    """Convert a Lark Tree to a zss-compatible tree (Node object)."""
    if isinstance(ttree, Token):
        return Node(str(ttree))  
    return Node(ttree.data, children=[lark_tree_to_zss(child) for child in ttree.children])

def calculate_tree_edit_distance(tree1, tree2):
    """Computes the Tree Edit Distance between two trees."""
    return simple_distance(tree1, tree2)

def get_tree_structure_with_order(node, parent_label=None):
    """Returns a list of (node_label, parent_label, ordered_children)."""
    children = [child.label for child in node.children]
    structure = [(node.label, parent_label, tuple(children))]
    for child in node.children:
        structure.extend(get_tree_structure_with_order(child, node.label))
    return structure

def pair_matching_nodes(structure1, structure2):
    """Pairs nodes with the same label and parent for more accurate comparison."""
    grouped1, grouped2 = defaultdict(list), defaultdict(list)
    
    for label, parent, children in structure1:
        grouped1[(label, parent)].append(children)
    for label, parent, children in structure2:
        grouped2[(label, parent)].append(children)

    matched_pairs = []
    for key in grouped1.keys() | grouped2.keys():
        list1, list2 = grouped1.get(key, []), grouped2.get(key, [])
        for i in range(min(len(list1), len(list2))):
            matched_pairs.append((key[0], list1[i], list2[i]))
        for extra in list1[len(list2):]:
            matched_pairs.append((key[0], extra, None))
        for extra in list2[len(list1):]:
            matched_pairs.append((key[0], None, extra))
    
    return matched_pairs

def highlight_tree_differences(tree1, tree2):
    """Highlights differences between two Lark parse trees."""
    zss_tree1, zss_tree2 = lark_tree_to_zss(tree1), lark_tree_to_zss(tree2)
    distance = calculate_tree_edit_distance(zss_tree1, zss_tree2)
    
    print("Tree Edit Distance (TED):", distance)
    print("\nChanged Nodes:")

    structure1, structure2 = get_tree_structure_with_order(zss_tree1), get_tree_structure_with_order(zss_tree2)
    paired_nodes = pair_matching_nodes(structure1, structure2)

    modified_nodes, added_nodes, removed_nodes, moved_nodes = [], set(), set(), []

    for node, old_children, new_children in paired_nodes:
        if old_children is None:
            added_nodes.add(node)
        elif new_children is None:
            removed_nodes.add(node)
        elif old_children != new_children:
            moved = [item for item in old_children if item in new_children and old_children.index(item) != new_children.index(item)]
            added, removed = set(new_children) - set(old_children), set(old_children) - set(new_children)

            if moved:
                moved_nodes.append((node, moved))
            if added or removed:
                modified_nodes.append((node, added, removed))

    for node, added, removed in modified_nodes:
        changes = []
        if added:
            changes.append(f"added {', '.join(added)}")
        if removed:
            changes.append(f"removed {', '.join(removed)}")
        print(f'Modified Command: {node} - ' + "; ".join(changes))

    for node, moved in moved_nodes:
        print(f'Moved Command: {node} - moved {", ".join(moved)}')

    if not (added_nodes or removed_nodes or modified_nodes or moved_nodes):
        print("No differences detected.")

    return distance
