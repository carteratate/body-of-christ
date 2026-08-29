import ast
from pathlib import Path


API_ROOT = Path(__file__).parents[1]
SOURCE_ROOTS = (API_ROOT / "app", API_ROOT / "scripts")
MESSAGE_METHODS = {"create", "stream", "parse", "count_tokens"}
REMOVED_SAMPLING_PARAMETERS = {"temperature", "top_p", "top_k"}


def test_anthropic_message_calls_do_not_use_removed_sampling_parameters():
    violations: list[str] = []

    for source_root in SOURCE_ROOTS:
        for path in source_root.rglob("*.py"):
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr not in MESSAGE_METHODS:
                    continue
                owner = node.func.value
                if not isinstance(owner, ast.Attribute) or owner.attr != "messages":
                    continue

                removed = sorted(
                    keyword.arg
                    for keyword in node.keywords
                    if keyword.arg in REMOVED_SAMPLING_PARAMETERS
                )
                if removed:
                    relative_path = path.relative_to(API_ROOT)
                    violations.append(f"{relative_path}:{node.lineno}: {', '.join(removed)}")

    assert violations == [], "Removed Anthropic message parameters:\n" + "\n".join(violations)
