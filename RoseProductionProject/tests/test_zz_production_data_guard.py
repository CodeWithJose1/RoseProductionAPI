"""Runs last (file name order): proves the test session left the existing
production data untouched and removed every record it created."""

from conftest import take_snapshot


def test_existing_rows_unchanged_and_no_test_rows_left(app, baseline):
    after = take_snapshot(app)
    for table, before_rows in baseline.items():
        after_rows = after[table]
        missing = set(before_rows) - set(after_rows)
        changed = [pk for pk in before_rows
                   if pk in after_rows and after_rows[pk] != before_rows[pk]]
        leftovers = set(after_rows) - set(before_rows)
        assert not missing, f"{table}: pre-existing rows deleted {missing}"
        assert not changed, f"{table}: pre-existing rows modified {changed}"
        assert not leftovers, f"{table}: test rows left behind {leftovers}"
