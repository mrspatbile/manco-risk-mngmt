"""Notebook code-contract tests for the four refactored fund notebooks.

Parses each target notebook and fails on:
- syntax errors and stored error outputs,
- def/class, raw SQL, ORM sessions, plt, .style, data-generator calls,
- inline investor/tenant/scenario datasets,
- empty code cells,
- headings joined to body text,
- duplicate banner / RMP / setup / Annex IV workflow calls.
"""

import ast
import json
import re
from pathlib import Path

import pytest

TARGETS = [
    'notebooks/funds/aifm_private_debt.ipynb',
    'notebooks/funds/aifm_real_estate.ipynb',
    'notebooks/funds/aifm_pe_buyout.ipynb',
    'notebooks/funds/aifm_infra_fund.ipynb',
]

FORBIDDEN_PATTERNS = {
    'def statement': re.compile(r'^\s*def\s', re.M),
    'class statement': re.compile(r'^\s*class\s', re.M),
    'raw SQL': re.compile(r'read_sql|sa\.text|text\(\s*["\']SELECT|SELECT\s+.+\s+FROM',
                          re.I),
    'ORM session': re.compile(r'\bSession\('),
    'engine connect': re.compile(r'ENGINE\.connect|\.connect\(\)'),
    'matplotlib pyplot': re.compile(r'\bplt\.'),
    'pandas Styler': re.compile(r'\.style\b'),
    'groupby': re.compile(r'\.groupby\('),
    'merge': re.compile(r'\.merge\('),
    'apply': re.compile(r'\.apply\('),
    'data generator call': re.compile(
        r'generate_pe_fund\(|generate_infra_fund\(|generate_cash_flows\(|'
        r'generate_valuation_reports\(|generate_positions\('),
    'inline investor register': re.compile(r'investor_name.+investor_name',
                                           re.S),
    'inline tenant register': re.compile(r'annual_rent_eur.+annual_rent_eur',
                                         re.S),
    'setup_db force': re.compile(r'setup_db\(\s*force'),
    'debug len print': re.compile(r'^\s*print\(len\(', re.M),
}


def _load(path):
    return json.loads(Path(path).read_text())


@pytest.fixture(params=TARGETS, ids=[Path(t).stem for t in TARGETS])
def notebook(request):
    return _load(request.param)


def _code_cells(nb):
    return [c for c in nb['cells'] if c['cell_type'] == 'code']


def _source(cell):
    return ''.join(cell['source'])


class TestNotebookContract:
    def test_code_cells_parse(self, notebook):
        for i, cell in enumerate(_code_cells(notebook)):
            ast.parse(_source(cell))

    def test_no_error_outputs(self, notebook):
        for cell in _code_cells(notebook):
            for out in cell.get('outputs', []):
                assert out.get('output_type') != 'error', (
                    f"stored error output: {out.get('ename')}")

    def test_execution_counts_ordered_when_present(self, notebook):
        # The repo strips notebook outputs via the nbstripout git filter
        # (.gitattributes), so committed notebooks carry no execution
        # counts. Only assert monotonic order when counts are present
        # (i.e. an executed working-tree copy); end-to-end execution is
        # verified separately by actually running the notebooks.
        counts = [c.get('execution_count') for c in _code_cells(notebook)]
        present = [c for c in counts if c is not None]
        assert present == sorted(present), 'out-of-order execution counts'

    def test_no_empty_code_cells(self, notebook):
        for cell in _code_cells(notebook):
            assert _source(cell).strip(), 'empty code cell'

    def test_no_forbidden_constructs(self, notebook):
        for cell in _code_cells(notebook):
            src = _source(cell)
            for label, pattern in FORBIDDEN_PATTERNS.items():
                assert not pattern.search(src), (
                    f'forbidden construct ({label}) in cell:\n{src[:300]}')

    def test_post_setup_cells_are_short(self, notebook):
        code = _code_cells(notebook)
        for cell in code[1:]:  # setup cell may be longer
            n_lines = len([l for l in _source(cell).splitlines()
                           if l.strip()])
            assert n_lines <= 12, (
                f'code cell exceeds 12 lines ({n_lines}):\n'
                f'{_source(cell)[:300]}')

    def test_headings_on_separate_lines(self, notebook):
        for cell in notebook['cells']:
            if cell['cell_type'] != 'markdown':
                continue
            for line in _source(cell).splitlines():
                m = re.match(r'^(#{1,4})\s*(.+)$', line)
                if m:
                    # A heading followed by a sentence-length blob suggests
                    # joined heading/body text from a malformed cell
                    assert len(m.group(2)) < 120, (
                        f'heading joined to body text: {line[:140]}')

    def test_no_ticket_ids_in_markdown(self, notebook):
        for cell in notebook['cells']:
            if cell['cell_type'] == 'markdown':
                assert not re.search(r'MRS-\d+', _source(cell)), (
                    'ticket ID in user-facing markdown')

    def test_single_banner_rmp_setup_annex(self, notebook):
        joined = '\n'.join(_source(c) for c in _code_cells(notebook))
        assert joined.count('display_fund_overview_banner') == 1
        assert joined.count('display_fund_rmp_parameters') == 1
        assert joined.count('setup_db()') == 1
        assert joined.count('annex_iv_workflow.run(') == 1

    def test_uses_repository_kernel(self, notebook):
        kernel = notebook['metadata']['kernelspec']['name']
        assert kernel == 'fund-risk-workflow'

    def test_annex_iv_sections_explicit(self, notebook):
        joined = '\n'.join(_source(c) for c in _code_cells(notebook))
        assert 'sections=' in joined, (
            'Annex IV workflow call must pass an explicit section set')
