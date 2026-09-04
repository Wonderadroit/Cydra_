import ast
from pathlib import Path

from cydra.graph_semantics import RELATION_RULES


ROOT = Path(__file__).resolve().parents[1]


def _production_connect_relations():
    relations = set()
    for path in sorted((ROOT / "cydra").glob("*.py")):
        if path.name == "graph_semantics.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr != "connect":
                continue
            if len(node.args) < 2:
                continue
            relation = node.args[1]
            if isinstance(relation, ast.Constant) and isinstance(relation.value, str):
                relations.add(relation.value)
    return relations


def test_production_connect_relations_are_registered_in_graph_semantics():
    relations = _production_connect_relations()
    missing = sorted(relations - set(RELATION_RULES))
    assert not missing, f"production graph relation(s) missing semantic rules: {missing}"
