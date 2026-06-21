# scripts/test_validate_frontmatter.py
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("vf", pathlib.Path(__file__).parent / "validate_frontmatter.py")
vf = importlib.util.module_from_spec(spec); spec.loader.exec_module(vf)

def test_extracts_frontmatter():
    assert "name: x" in vf.extract_frontmatter("---\nname: x\ndescription: \"y\"\n---\nbody")

def test_unquoted_colon_space_is_error(tmp_path):
    d = tmp_path / "skills" / "demo"; d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: demo\ndescription: Use when: bad\n---\n")
    errs = vf.validate_skill(d / "SKILL.md")
    assert any("mapping" in e or "description" in e for e in errs)

def test_name_must_match_dir(tmp_path):
    d = tmp_path / "skills" / "demo"; d.mkdir(parents=True)
    (d / "SKILL.md").write_text('---\nname: wrong\ndescription: "ok"\n---\n')
    assert any("!= directory" in e for e in vf.validate_skill(d / "SKILL.md"))

def test_valid_skill_has_no_errors(tmp_path):
    d = tmp_path / "skills" / "demo"; d.mkdir(parents=True)
    (d / "SKILL.md").write_text('---\nname: demo\ndescription: "ok"\n---\n')
    assert vf.validate_skill(d / "SKILL.md") == []
