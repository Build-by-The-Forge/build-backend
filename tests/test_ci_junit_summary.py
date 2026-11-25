"""scripts/ci_junit_summary.py: a red test run's failures, from its JUnit report,
for the job summary. Reporting only: it always exits 0 and never raises."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ci_junit_summary", ROOT / "scripts" / "ci_junit_summary.py")
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)

PASSING = '<testsuite><testcase classname="tests.a" name="test_ok"/></testsuite>'
FAILING = """<testsuites><testsuite>
<testcase classname="tests.a" name="test_ok"/>
<testcase classname="tests.b" name="test_bad">
<failure message="assert 1 == 2">    def test_bad():
&gt;       assert 1 == 2
E       assert 1 == 2
E        +  where 1 = f()
</failure></testcase>
<testcase classname="tests.c" name="test_err"><error message="boom `tick`">no E lines here</error></testcase>
</testsuite></testsuites>"""


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_a_missing_report_says_the_tests_did_not_finish(tmp_path):
    text = summary.summarise([str(tmp_path / "pytest-junit.xml")])
    assert "did not finish" in text


def test_a_green_run_reports_its_count_and_lists_nothing(tmp_path):
    text = summary.summarise([write(tmp_path, "a.xml", PASSING)])
    assert text == "### Tests: 1 run, 0 failing or erroring"


def test_failures_and_errors_are_listed_with_their_error_lines(tmp_path):
    text = summary.summarise([write(tmp_path, "a.xml", FAILING)])
    assert "### Tests: 3 run, 2 failing or erroring" in text
    assert "`tests.b::test_bad` (`a.xml`)" in text
    assert "`E       assert 1 == 2`" in text and "`E        +  where 1 = f()`" in text
    # An error with no E lines falls back to its message, and a backtick can't break the Markdown.
    assert "`tests.c::test_err` (`a.xml`)" in text and "`boom 'tick'`" in text


def test_reports_from_several_steps_are_combined(tmp_path):
    text = summary.summarise([write(tmp_path, "a.xml", PASSING), write(tmp_path, "b.xml", FAILING)])
    assert "### Tests: 4 run, 2 failing or erroring" in text
    # Each failure names the report it came from, so which pytest invocation.
    assert "`tests.b::test_bad` (`b.xml`)" in text and "(`a.xml`)" not in text


def test_an_unreadable_report_is_said_so_and_the_rest_still_count(tmp_path):
    text = summary.summarise([write(tmp_path, "bad.xml", "<testsuite><oops"), write(tmp_path, "a.xml", FAILING)])
    assert "`bad.xml` could not be read" in text
    assert "### Tests: 3 run, 2 failing or erroring" in text


def test_a_long_failure_list_is_cut_and_says_how_many_more(tmp_path):
    cases = "".join(f'<testcase classname="t" name="test_{i}"><failure message="m"/></testcase>' for i in range(75))
    text = summary.summarise([write(tmp_path, "many.xml", f"<testsuite>{cases}</testsuite>")])
    assert text.count("- `t::test_") == 60
    assert "... and 15 more" in text


def test_a_very_long_error_line_is_shortened(tmp_path):
    xml = f'<testsuite><testcase classname="t" name="x"><failure message="m">E {"x" * 500}</failure></testcase></testsuite>'
    text = summary.summarise([write(tmp_path, "long.xml", xml)])
    assert max(len(line) for line in text.splitlines()) < 230


def test_main_always_exits_zero_whatever_the_report(tmp_path, capsys):
    for args in ([], [str(tmp_path / "nope.xml")], [write(tmp_path, "bad.xml", "not xml")], [write(tmp_path, "f.xml", FAILING)]):
        assert summary.main(["ci_junit_summary.py", *args]) == 0
    assert "failing or erroring" in capsys.readouterr().out
