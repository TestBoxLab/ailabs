"""Display yes, export no (Lucas, 11 September 2026).

One report shows every setup that ran, a lab build included. What a lab build may not do is leave
the machine — the rule the retired audiences file stated as "a lab competitor can never reach an
exportable artifact". So the report carries `lab_setups`, and the interface refuses to save or
print while it is non-empty: refuses, rather than quietly rendering a thinner page, because a
reader cannot tell what is missing from one of those."""
import re
from pathlib import Path

import pytest

from wb_studio import report_data

STATIC = Path(__file__).resolve().parents[1] / 'wb_studio' / 'static'
SETUPS = {'a': {'name': 'monarch@1.4.0'}, 'lab-1': {'name': 'monarch-lab-retry'}, 'b': {'name': 'Bare'}}


def test_what_counts_as_a_lab_build():
    """Self-contained on purpose. This predicate used to be checked against the CLI's copy; the CLI
    gate and its audiences file were retired on 11 September, so there is nothing left to agree
    with and a test that imported it would break on someone else's deletion."""
    for name in ('monarch-lab', 'monarch-lab-retry', 'monarch-lab2'):
        assert report_data.is_lab(name) is True
    for name in ('monarch', 'monarch@1.4.0', 'Bare', 'gpt-5.6-sol', '', None, 'lab-monarch'):
        assert report_data.is_lab(name) is False


def test_a_lab_build_is_found_by_id_or_by_name():
    found = report_data.lab_setups(['a', 'lab-1', 'b'], SETUPS)
    assert found == [{'id': 'lab-1', 'name': 'monarch-lab-retry'}]
    # By id too, in case a setup is named something friendlier than its id.
    assert report_data.lab_setups(['monarch-lab-x'], {}) == [{'id': 'monarch-lab-x', 'name': 'monarch-lab-x'}]
    assert report_data.lab_setups(['a', 'b'], SETUPS) == []
    assert report_data.lab_setups(None, None) == []


def test_both_report_kinds_carry_the_list():
    source = (Path(__file__).resolve().parents[1] / 'wb_studio' / 'report_data.py').read_text(encoding='utf8')
    assert source.count('"lab_setups": lab_setups(shown, m["setups"])') == 2   # run report and round report


def test_the_report_still_shows_the_lab_build():
    """The gate is on leaving, not on looking: nothing here filters `order` or `setups`."""
    source = (Path(__file__).resolve().parents[1] / 'wb_studio' / 'report_data.py').read_text(encoding='utf8')
    assert 'visible_setups' not in source and 'hidden_setups' not in source
    assert 'There is one report' in source


# -- the interface refuses, by either route -------------------------------------------

def test_save_and_print_both_ask_the_gate_first():
    js = (STATIC / 'reports.js').read_text(encoding='utf8')
    assert "print.onclick = () => { if (!labGate(r, 'print')) window.print(); }" in js
    assert "save.onclick = () => { if (!labGate(r, 'save')) saveReportHtml(article, r); }" in js
    gate = js[js.index('function labGate'):js.index('// The export is one file')]
    assert "if (!lab.length) return false" in gate and 'return true' in gate
    assert 'toast(' in gate and 'may not leave the machine' in gate
    # It refuses; it does not strip rows out and ship a thinner file.
    assert 'remove()' not in gate and 'filter' not in gate


def test_ctrl_p_cannot_walk_around_the_button():
    js = (STATIC / 'reports.js').read_text(encoding='utf8')
    css = (STATIC / 'report.css').read_text(encoding='utf8')
    assert "article.classList.toggle('lab-present', !!(r.lab_setups || []).length)" in js
    rule = re.search(r'@media print\{\.report\.lab-present>\*\{display:none\}[^}]*\}[^}]*\}', css)
    assert rule, 'the print stylesheet must blank a report that carries a lab build'
    assert 'may not leave the machine' in rule.group(0)


def test_the_gate_carries_no_colour_of_its_own():
    """The CSS guard forbids hex, !important, inline styles and external resources; the added rule
    obeys the design system like everything else."""
    css = (STATIC / 'report.css').read_text(encoding='utf8')
    added = css[css.index('Display yes, export no'):]
    assert '#' not in added and '!important' not in added and 'http' not in added
    assert 'var(--font-prose)' in added
