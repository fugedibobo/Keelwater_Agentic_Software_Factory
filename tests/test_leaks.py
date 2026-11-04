import ast
from pathlib import Path
import re
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generator.specs import ROOT, load


def violations(source, path):
    normalised = source.replace('\\', '/')
    issues = []
    if 'data/ground_truth.yaml' in normalised or 'generator/spec' in normalised:
        issues.append('ground truth or generator spec')
    if re.search(r'data/holdout/(?!raw(?=$|[\s/\'"`]))', normalised) or 'data/holdout/raw/..' in normalised:
        issues.append('held-out answer')
    if 'data/holdout/raw' in normalised and path.as_posix() not in ('pipeline.py', 'cli.py'):
        issues.append('held-out input outside entry points')
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(n.name == 'generator' or n.name.startswith('generator.') for n in node.names) and path.as_posix() != 'cli.py':
            issues.append('generator import')
        if isinstance(node, ast.ImportFrom) and (node.module == 'generator' or (node.module or '').startswith('generator.')) and path.as_posix() != 'cli.py':
            issues.append('generator import')
        if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) and path.as_posix() != 'cli.py':
            is_import = isinstance(node.func, ast.Name) and node.func.id == '__import__' or isinstance(node.func, ast.Attribute) and node.func.attr == 'import_module'
            if is_import and (node.args[0].value == 'generator' or node.args[0].value.startswith('generator.')):
                issues.append('generator import')
    return issues


def test_pipeline_cannot_read_generator_truth():
    pipeline = ROOT / 'signal_engine'
    if not pipeline.exists():
        pipeline = ROOT / '.scratch' / 'issue1' / 'signal_engine'
    if not pipeline.exists():
        pytest.skip('issue #1 pipeline not present')
    for path in pipeline.rglob('*.py'):
        if 'evals' in path.relative_to(pipeline).parts:
            continue
        assert not violations(path.read_text(encoding='utf-8'), path.relative_to(pipeline)), path


def test_heldout_input_exception_does_not_expose_answers():
    assert not violations('x = "data/holdout/raw"', Path('pipeline.py'))
    assert violations('x = "data/holdout/ground_truth.yaml"', Path('pipeline.py'))
    assert violations('x = "data/holdout/raw/../ground_truth.yaml"', Path('pipeline.py'))
    assert violations('x = "data/holdout/raw"', Path('other.py'))
    assert violations('import generator', Path('pipeline.py'))
    assert violations('import importlib\nimportlib.import_module("generator.specs")', Path('pipeline.py'))
    assert not violations('import generator', Path('cli.py'))


def test_theme_terms_absent_from_exposed_files():
    for folder in ('data/raw', 'data/holdout/raw', 'generator/prompts', 'config'):
        terms = []
        for seed in (42, 43):
            for theme in load(seed)['themes']['themes']:
                terms.extend([theme['id'], theme['title'], *theme['facts']])
                if folder in ('generator/prompts', 'config'):
                    terms.extend(theme['synonyms'])
        base = ROOT / folder
        for path in base.rglob('*') if base.exists() else ():
            if path.is_file():
                content = path.read_text(encoding='utf-8').casefold()
                assert not any(term and term.casefold() in content for term in terms), path
        if folder == 'config' and not (base / 'taxonomy.yaml').exists():
            taxonomy = ROOT / '.scratch' / 'issue1' / 'config' / 'taxonomy.yaml'
            if taxonomy.exists():
                content = taxonomy.read_text(encoding='utf-8').casefold()
                assert not any(term and term.casefold() in content for term in terms), taxonomy
