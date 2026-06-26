import argparse
import re
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass
from difflib import SequenceMatcher


FX_OPCODES = {
    'placeholder', 'call_module', 'call_function',
    'call_method', 'get_attr', 'output'
}


@dataclass
class GraphNode:
    """Graph node representation."""
    line_num: int
    raw_line: str
    node_type: str  # opcode
    target: str     # operation target
    args: str       # arguments
    kwargs: str     # keyword arguments
    output: str     # output variable name
    name: str       # node name


@dataclass
class NodeDiffResult:
    """Difference result between two graph nodes."""
    idx_1: int
    idx_2: int
    node_1: Optional[GraphNode]
    node_2: Optional[GraphNode]
    diff_type: str  # 'diff', 'only_in_1', 'only_in_2'
    diff_fields: List[str]  # fields that differ
    similarity: float
    category: str   # 'operator_change', 'parameter_change', 'structure_change'


def extract_table_column_spans(
    header_line: str
) -> List[Tuple[str, int, int]]:
    """Extract column spans from table-format header line."""
    matches = list(re.finditer(r'\S+', header_line))
    names = [m.group(0) for m in matches]
    expected = ['opcode', 'name', 'target', 'args', 'kwargs']
    assert names == expected, f'Invalid table header columns: {names}, expected: {expected}'

    spans: List[Tuple[str, int, int]] = []
    row_end = len(header_line.rstrip('\n'))
    for idx, m in enumerate(matches[:len(expected)]):
        start = m.start()
        end = matches[idx + 1].start() if idx + 1 < len(expected) else row_end
        spans.append((m.group(0), start, end))

    return spans


def parse_fx_graph_line(
    line: str,
    column_spans: List[Tuple[str, int, int]]
) -> Optional[GraphNode]:
    """Parse a single line of FX graph content."""
    raw_line = line.rstrip('\n')
    stripped = raw_line.strip()

    if not stripped or stripped.startswith('---'):
        return None

    # Parse table-format lines based on header column spans.
    fields = {}
    for col_name, start, end in column_spans:
        part = raw_line[start:end]
        fields[col_name] = part.strip()

    if fields.get('opcode') in FX_OPCODES:
        return GraphNode(
            raw_line=stripped,
            line_num=0,
            node_type=fields.get('opcode', ''),
            name=fields.get('name', ''),
            target=fields.get('target', ''),
            args=fields.get('args', ''),
            kwargs=fields.get('kwargs', ''),
            output=''
        )

    # If not matching standard format, return as raw node
    return GraphNode(
        raw_line=stripped,
        line_num=0,
        node_type='raw',
        target='',
        args='',
        kwargs='',
        output='',
        name=''
    )


def load_fx_graph(filepath: str) -> List[GraphNode]:
    """Load FX graph file and return parsed nodes."""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    nodes = []
    column_spans: Optional[List[Tuple[str, int, int]]] = None

    for i, line in enumerate(lines):
        if column_spans is None and line.strip().startswith('opcode'):
            column_spans = extract_table_column_spans(line)
        elif column_spans is not None:
            node = parse_fx_graph_line(line, column_spans)
            if node:
                node.line_num = i + 1
                nodes.append(node)

    return nodes


def normalize_field(value: str) -> str:
    """Normalize field value for comparison."""
    value = re.sub(r'\s+', ' ', value.strip())
    return value


def compare_nodes(node1: GraphNode, node2: GraphNode) -> Tuple[float, List[str]]:
    """Compare two nodes and return similarity and list of differing fields."""
    if node1 is None or node2 is None:
        return 0.0, ['missing']

    # Ignore framework sentinel node differences (e.g. function address jitter).
    if (
        node1.node_type == 'call_function' and node2.node_type == 'call_function'
        and node1.name == 'scope_end' and node2.name == 'scope_end'
    ):
        return 1.0, []

    diff_fields = []

    # Compare each field
    if normalize_field(node1.node_type) != normalize_field(node2.node_type):
        diff_fields.append('node_type')

    if normalize_field(node1.target) != normalize_field(node2.target):
        diff_fields.append('target')

    if normalize_field(node1.args) != normalize_field(node2.args):
        diff_fields.append('args')

    if normalize_field(node1.kwargs) != normalize_field(node2.kwargs):
        diff_fields.append('kwargs')

    if normalize_field(node1.output) != normalize_field(node2.output):
        diff_fields.append('output')

    if normalize_field(node1.name) != normalize_field(node2.name):
        diff_fields.append('name')

    # Calculate overall similarity based on raw lines
    similarity = SequenceMatcher(
        None, node1.raw_line, node2.raw_line
    ).ratio()

    return similarity, diff_fields


def categorize_diff(node1: Optional[GraphNode],
                    node2: Optional[GraphNode],
                    diff_fields: List[str]) -> str:
    """Categorize the type of difference."""
    if node1 is None or node2 is None:
        return 'structure_change'

    if 'target' in diff_fields:
        return 'operator_change'

    if 'args' in diff_fields or 'kwargs' in diff_fields:
        return 'parameter_change'

    # Default to structure change
    return 'structure_change'


def calculate_node_similarity(
    nodes1: List[GraphNode],
    nodes2: List[GraphNode]
) -> Tuple[float, Optional[NodeDiffResult], List[NodeDiffResult]]:
    """Calculate similarity and collect first/all node differences in one pass."""
    differences: List[NodeDiffResult] = []
    matches = 0

    max_len = max(len(nodes1), len(nodes2))
    if max_len == 0:
        return 1.0, None, differences

    for i in range(max_len):
        n1 = nodes1[i] if i < len(nodes1) else None
        n2 = nodes2[i] if i < len(nodes2) else None

        if n1 is None:
            diff_result = NodeDiffResult(
                idx_1=i,
                idx_2=i,
                node_1=None,
                node_2=n2,
                diff_type='only_in_2',
                diff_fields=['missing'],
                similarity=0.0,
                category='structure_change'
            )
            differences.append(diff_result)
            continue

        if n2 is None:
            diff_result = NodeDiffResult(
                idx_1=i,
                idx_2=i,
                node_1=n1,
                node_2=None,
                diff_type='only_in_1',
                diff_fields=['missing'],
                similarity=0.0,
                category='structure_change'
            )
            differences.append(diff_result)
            continue

        similarity, diff_fields = compare_nodes(n1, n2)
        if not diff_fields:
            matches += 1
            continue

        diff_result = NodeDiffResult(
            idx_1=i,
            idx_2=i,
            node_1=n1,
            node_2=n2,
            diff_type='diff',
            diff_fields=diff_fields,
            similarity=similarity,
            category=categorize_diff(n1, n2, diff_fields)
        )
        differences.append(diff_result)

    first_diff = differences[0] if differences else None
    return matches / max_len, first_diff, differences


def write_comparison_report(
    file1: str,
    file2: str,
    nodes1: List[GraphNode],
    nodes2: List[GraphNode],
    output_file: str
):
    """Write detailed comparison report to file."""
    with open(output_file, 'w', encoding='utf-8') as output_stream:
        output_stream.write("=" * 80 + "\n")
        output_stream.write("FX Graph Comparison Report (Node-Based)\n")
        output_stream.write("=" * 80 + "\n")
        output_stream.write(f"File 1: {file1}\n")
        output_stream.write(f"File 2: {file2}\n")
        output_stream.write(f"Graph 1 total nodes: {len(nodes1)}\n")
        output_stream.write(f"Graph 2 total nodes: {len(nodes2)}\n\n")

        overall_similarity, first_diff, all_diffs = calculate_node_similarity(
            nodes1, nodes2
        )
        output_stream.write(f"Overall node similarity: {overall_similarity:.2%}\n\n")

        if first_diff is None:
            output_stream.write("The two computation graphs are identical!\n")
            return

        output_stream.write("Differences found\n")
        output_stream.write("-" * 80 + "\n")
        output_stream.write("First difference location:\n")
        output_stream.write(f"   Node index: {first_diff.idx_1}\n")
        output_stream.write(f"   Difference type: {first_diff.diff_type}\n")
        output_stream.write(
            f"   Difference fields: {', '.join(first_diff.diff_fields)}\n"
        )
        output_stream.write(f"   Difference category: {first_diff.category}\n\n")

        output_stream.write("Difference content:\n")
        if first_diff.node_1:
            output_stream.write(
                f"   File 1 [line {first_diff.node_1.line_num}]:\n"
            )
            output_stream.write(f"      {first_diff.node_1.raw_line}\n")
            output_stream.write(f"      node_type: {first_diff.node_1.node_type}\n")
            output_stream.write(f"      name: {first_diff.node_1.name}\n")
            output_stream.write(f"      target: {first_diff.node_1.target}\n")
            output_stream.write(f"      args: {first_diff.node_1.args}\n")
        else:
            output_stream.write("   File 1: <missing>\n")

        output_stream.write("\n")
        if first_diff.node_2:
            output_stream.write(
                f"   File 2 [line {first_diff.node_2.line_num}]:\n"
            )
            output_stream.write(f"      {first_diff.node_2.raw_line}\n")
            output_stream.write(f"      node_type: {first_diff.node_2.node_type}\n")
            output_stream.write(f"      name: {first_diff.node_2.name}\n")
            output_stream.write(f"      target: {first_diff.node_2.target}\n")
            output_stream.write(f"      args: {first_diff.node_2.args}\n")
        else:
            output_stream.write("   File 2: <missing>\n")

        if first_diff.similarity > 0:
            output_stream.write(
                f"\n   Line similarity: {first_diff.similarity:.2%}\n"
            )

        output_stream.write("\n")
        output_stream.write("Context (2 nodes before and after):\n")
        output_stream.write("-" * 80 + "\n")

        # File 1 context
        if first_diff.diff_type == 'only_in_2':
            output_stream.write("File 1: <no corresponding node>\n")
        else:
            context_start = max(0, first_diff.idx_1 - 2)
            context_end = min(len(nodes1), first_diff.idx_1 + 3)
            output_stream.write("File 1:\n")
            for i in range(context_start, context_end):
                marker = ">>> " if i == first_diff.idx_1 else "    "
                node = nodes1[i]
                output_stream.write(
                    f"{marker}[{i}] {node.node_type} | {node.name} | {node.target}\n"
                )

        output_stream.write("\n")
        # File 2 context
        if first_diff.diff_type == 'only_in_1':
            output_stream.write("File 2: <no corresponding node>\n")
        else:
            context_start = max(0, first_diff.idx_2 - 2)
            context_end = min(len(nodes2), first_diff.idx_2 + 3)
            output_stream.write("File 2:\n")
            for i in range(context_start, context_end):
                marker = ">>> " if i == first_diff.idx_2 else "    "
                node = nodes2[i]
                output_stream.write(
                    f"{marker}[{i}] {node.node_type} | {node.name} | {node.target}\n"
                )

        output_stream.write("\n")
        output_stream.write("=" * 80 + "\n")
        output_stream.write("All Differences Statistics\n")
        output_stream.write("=" * 80 + "\n")

        if all_diffs:
            output_stream.write(f"Total differences found: {len(all_diffs)}\n")
            categories = {}
            for diff in all_diffs:
                cat = diff.category
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(diff)

            output_stream.write("\n")
            for category, diffs in categories.items():
                output_stream.write(
                    f"\n{category.upper()} ({len(diffs)} occurrences):\n"
                )
                output_stream.write("-" * 80 + "\n")

                for i, diff in enumerate(diffs[:5], 1):
                    output_stream.write(f"{i}. Node index {diff.idx_1}\n")
                    output_stream.write(
                        f"   Diff fields: {', '.join(diff.diff_fields)}\n"
                    )
                    if diff.node_1:
                        output_stream.write(
                            f"   File 1: {diff.node_1.raw_line[:60]}...\n"
                        )
                    if diff.node_2:
                        output_stream.write(
                            f"   File 2: {diff.node_2.raw_line[:60]}...\n"
                        )
                    if diff.similarity > 0:
                        output_stream.write(
                            f"   Similarity: {diff.similarity:.2%}\n"
                        )
                    output_stream.write("\n")

                if len(diffs) > 5:
                    output_stream.write(
                        f"   ... ({len(diffs) - 5} more differences)\n"
                    )
        else:
            output_stream.write("No differences found\n")

        output_stream.write("\n")
        output_stream.write("=" * 80 + "\n")
        output_stream.write("Statistics\n")
        output_stream.write("=" * 80 + "\n")
        output_stream.write(f"Overall node similarity: {overall_similarity:.2%}\n")

        only_in_1_count = sum(1 for d in all_diffs if d.diff_type == 'only_in_1')
        only_in_2_count = sum(1 for d in all_diffs if d.diff_type == 'only_in_2')
        output_stream.write(f"Nodes only in file 1: {only_in_1_count}\n")
        output_stream.write(f"Nodes only in file 2: {only_in_2_count}\n")


def compare_fx_graphs(
    file1: str,
    file2: str,
    output_file: str
):
    nodes1 = load_fx_graph(file1)
    nodes2 = load_fx_graph(file2)
    write_comparison_report(file1, file2, nodes1, nodes2, output_file)


def main():
    parser = argparse.ArgumentParser(
        description='Compare two FX Graph files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
            Example usage:
            # Output to file
            python j6_plugin_graph_diff.py --file1 graph1.txt --file2 graph2.txt -o report.txt
        """
    )

    parser.add_argument(
        '--file1',
        required=True,
        help='First FX graph file path'
    )

    parser.add_argument(
        '--file2',
        required=True,
        help='Second FX graph file path'
    )

    parser.add_argument(
        '-o', '--output',
        required=True,
        help='Output report file path (required)'
    )

    args = parser.parse_args()
    compare_fx_graphs(args.file1, args.file2, args.output)


if __name__ == '__main__':
    main()
