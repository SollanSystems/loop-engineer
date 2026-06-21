# scripts/validate_frontmatter.py
import sys, pathlib, yaml

def extract_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        raise ValueError("no frontmatter block")
    end = text.index("\n---", 3)
    return text[3:end]

def validate_skill(path) -> list:
    errors = []
    path = pathlib.Path(path)
    raw = path.read_text(encoding="utf-8")
    try:
        fm = yaml.safe_load(extract_frontmatter(raw))
    except Exception as e:
        return [f"{path}: frontmatter does not parse ({e}); likely a stray ': ' in an unquoted scalar"]
    if not isinstance(fm, dict):
        return [f"{path}: frontmatter is not a mapping (likely a stray ': ' in an unquoted scalar)"]
    for key in ("name", "description"):
        if not isinstance(fm.get(key), str) or not fm[key].strip():
            errors.append(f"{path}: missing/empty '{key}'")
    if isinstance(fm.get("name"), str) and fm["name"] != path.parent.name:
        errors.append(f"{path}: name '{fm['name']}' != directory '{path.parent.name}'")
    return errors

def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    skills = sorted((root / "skills").glob("*/SKILL.md"))
    all_errors = [e for s in skills for e in validate_skill(s)]
    for e in all_errors:
        print("FAIL:", e)
    print(f"checked {len(skills)} skills, {len(all_errors)} errors")
    return 1 if all_errors else 0

if __name__ == "__main__":
    sys.exit(main())
