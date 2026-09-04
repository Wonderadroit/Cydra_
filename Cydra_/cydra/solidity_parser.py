from __future__ import annotations

import re
from pathlib import Path

from .repository_model import RepositoryModel, SourceContract, SourceFunction


_CONTRACT_RE = re.compile(r"\bcontract\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)")
_FUNCTION_RE = re.compile(
    r"\bfunction\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*(?P<tail>[^{};]*)"
)
_MODIFIER_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*(?:\([^;{}]*\))?")
_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_STATE_RE = re.compile(
    r"^\s*(?P<type>mapping\s*\([^;]*\)|[A-Za-z_][A-Za-z0-9_<>\[\]]*(?:\s+payable)?)\s+"
    r"(?:(?:public|private|internal|external|constant|immutable|transient)\s+)*"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?:=[^;]*)?;"
)


def _matching_brace(text: str, opening: int) -> int | None:
    """Return the matching closing brace for an opening brace."""
    depth = 0
    for index in range(opening, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def parse_solidity_file(path: str | Path) -> list[SourceContract]:
    """Extract a conservative structural model without pretending to be a full compiler parser."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    contracts: list[SourceContract] = []

    matches = list(_CONTRACT_RE.finditer(text))
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end]
        functions: list[SourceFunction] = []
        for fm in _FUNCTION_RE.finditer(body):
            tail = fm.group("tail")
            modifiers = tuple(
                token for token in _MODIFIER_RE.findall(tail)
                if token not in {"public", "private", "internal", "external", "view", "pure", "payable"}
            )
            calls: tuple[str, ...] = ()
            opening = body.find("{", fm.end())
            if opening != -1:
                closing = _matching_brace(body, opening)
                if closing is not None:
                    function_body = body[opening : closing + 1]
                    calls = tuple(f"{obj}.{method}" for obj, method in _CALL_RE.findall(function_body))
            visibility = next((v for v in ("public", "private", "internal", "external") if re.search(rf"\b{v}\b", tail)), None)
            line = body[:fm.start()].count("\n") + 1
            functions.append(SourceFunction(fm.group("name"), str(path), line, visibility, modifiers, calls))

        state_variables = tuple(
            m.group("name") for line in body.splitlines() if (m := _STATE_RE.match(line))
        )
        contracts.append(SourceContract(match.group("name"), str(path), tuple(functions), state_variables))
    return contracts


def build_repository_model(root: str | Path) -> RepositoryModel:
    from .repository_model import discover_source_files

    files = discover_source_files(root)
    contracts = [contract for path in files for contract in parse_solidity_file(path)]
    return RepositoryModel(str(Path(root)), contracts)
