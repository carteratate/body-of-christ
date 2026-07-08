import json
from enrichment.backup import Backup, import_backup


def test_write_appends_lines(tmp_path):
    b = Backup(str(tmp_path))
    b.write("bible", {"chunk_id": "c1", "stage": "generation"})
    b.write("bible", {"chunk_id": "c1", "stage": "classification"})
    lines = (tmp_path / "bible.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["stage"] == "generation"
    assert "ts" in json.loads(lines[0])


def test_write_is_append_only(tmp_path):
    b = Backup(str(tmp_path))
    b.write("summa", {"chunk_id": "c1"})
    Backup(str(tmp_path)).write("summa", {"chunk_id": "c2"})
    lines = (tmp_path / "summa.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2


def test_import_backup_file_and_dir(tmp_path):
    b = Backup(str(tmp_path))
    b.write("a", {"chunk_id": "a1"})
    b.write("b", {"chunk_id": "b1"})
    file_records = list(import_backup(str(tmp_path / "a.jsonl")))
    assert file_records == [ {**file_records[0]} ] and file_records[0]["chunk_id"] == "a1"
    dir_records = list(import_backup(str(tmp_path)))
    assert {r["chunk_id"] for r in dir_records} == {"a1", "b1"}
