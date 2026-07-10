"""Deterministic structural self-eval for the loop-engineer suite.

Runs the 13 structural checks the suite grades itself by (the hard pass/fail
gate for suite structure; the rubric in evals/rubric.md is the advisory layer
above this). Most checks are documentation-completeness scans — they confirm the
canonical vocabulary (terminal states, repair-record fields, eval layers +
metrics) is present in the skill prose, not that a running loop enforces it. The
runtime/behavioral gate is ``loop doctor`` and the contract's own ``verify-*``
scripts. Reuses ``validate_frontmatter`` from this same scripts/ dir rather than
reimplementing the frontmatter parse. Expected structural facts live in
``evals/cases/structural.json`` so the checks stay data-driven and in sync with
the suite.

Run:
    uv run --with pyyaml python3 scripts/self_eval.py .
"""

import json
import pathlib
import re
import sys

import validate_frontmatter as vf

# Known sibling skills the suite deliberately cross-links but does not ship
# (named in the spec reuse contract). A [[link]] to one of these resolves.
EXTERNAL_SKILLS = {"launch-local-agent"}

# Secret-shape patterns (boundary-focused, low false-positive). Mirrors the
# workspace redact stance: secret-shaped literals, not env-var names. The
# provider prefixes are assembled from fragments so this detector file does not
# itself contain a literal credential-shaped token.
_P = "-"  # prefix-joiner fragment, keeps "s" + "k" + _P apart from the literal
SECRET_PATTERNS = {
    "aws_access_key": re.compile("A" + "KIA" + r"[0-9A-Z]{16}"),
    "private_key_block": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"
    ),
    "vendor_key": re.compile(r"\b" + "s" + "k" + _P + r"[A-Za-z0-9_-]{20,}\b"),
    "slack_token": re.compile(r"\b" + "x" + "ox" + r"[baprs]-[A-Za-z0-9-]{10,}\b"),
    "github_pat": re.compile(r"\b" + "g" + "hp_" + r"[A-Za-z0-9]{36}\b"),
    "assigned_secret": re.compile(
        r"(?i)(api[_-]?key|secret|passwd|password|token)\s*[:=]\s*"
        r"['\"][^'\"\s]{8,}['\"]"
    ),
}

_DISPATCH_RE = re.compile(r"subagent_type|agent\s*\(", re.IGNORECASE)
_FENCE_RE = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)
_TEXT_SUFFIXES = {".md", ".py", ".js", ".json", ".tmpl", ".sh", ".txt", ""}


def _norm(text: str) -> str:
    """Lowercase + collapse every non-alphanumeric run to a single space."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_facts(root: pathlib.Path) -> dict:
    return json.loads(_read(root / "evals" / "cases" / "structural.json"))


def _skill_paths(root: pathlib.Path) -> list:
    return sorted((root / "skills").glob("*/SKILL.md"))


def _skill_dirs(root: pathlib.Path) -> set:
    return {p.parent.name for p in _skill_paths(root)}


def _skill_texts(root: pathlib.Path) -> dict:
    return {p.parent.name: _read(p) for p in _skill_paths(root)}


# Match a failure_mode VALUE assignment in Markdown — the label, then a
# colon/equals separator, then the quoted token — with no comma or backtick in
# between (so a prose list of field NAMES like "`failure_mode`, `hypothesis`"
# is not mistaken for a value).
_FM_MD_RE = re.compile(
    r"failure[_ ]mode[`*\s]*[:=][`*\s]*[`\"']([a-z][a-z-]+)[`\"']", re.IGNORECASE
)


def _json_failure_modes(obj) -> list:
    """Every value under a ``failure_mode`` key anywhere in a parsed JSON tree."""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "failure_mode" and isinstance(v, str):
                found.append(v)
            else:
                found.extend(_json_failure_modes(v))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_json_failure_modes(item))
    return found


def _scan_failure_modes(base: pathlib.Path, taxonomy: set) -> list:
    """Failure_mode values in examples/ that fall outside the canonical taxonomy.

    Closes the detection gap where an example could carry a non-canonical enum
    (e.g. ``coverage_below_threshold``) and still pass the field-name check.
    Scans JSON structurally and Markdown via a labelled-token regex.
    """
    bad = []
    if not base.exists():
        return bad
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix == ".json":
            try:
                values = _json_failure_modes(json.loads(_read(p)))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                continue
        elif p.suffix == ".md":
            try:
                values = _FM_MD_RE.findall(_read(p))
            except (OSError, UnicodeDecodeError):
                continue
        else:
            continue
        for v in values:
            if v not in taxonomy:
                bad.append(f"{p.relative_to(base.parent)}:{v}")
    return bad


def _iter_suite_files(root: pathlib.Path, scope) -> list:
    files = []
    for sub in scope:
        base = root / sub
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or "__pycache__" in p.parts:
                continue
            if p.suffix not in _TEXT_SUFFIXES:
                continue
            files.append(p)
    return files


# --- the 13 checks -----------------------------------------------------------
# Each returns (ok: bool, detail: str).


def check_all_skills_present(root, facts):
    expected = set(facts["skill_names"])
    have = _skill_dirs(root)
    missing = sorted(expected - have)
    if missing:
        return False, f"missing skills: {missing}"
    return True, f"all {len(expected)} skills present"


def check_frontmatter_valid(root, facts):
    errors = [e for p in _skill_paths(root) for e in vf.validate_skill(p)]
    if errors:
        return False, "; ".join(errors)
    return True, f"{len(_skill_paths(root))} SKILL.md frontmatter blocks parse"


def check_references_used(root, facts):
    texts = "\n".join(_skill_texts(root).values())
    ref_files = sorted((root / "reference").glob("*.md"))
    unused = [p.name for p in ref_files if p.name not in texts]
    if unused:
        return False, f"reference files not cited by any SKILL.md: {unused}"
    return True, f"all {len(ref_files)} reference files cited"


def check_links_resolve(root, facts):
    dirs = _skill_dirs(root) | EXTERNAL_SKILLS
    dangling = set()
    for name, text in _skill_texts(root).items():
        for target in re.findall(r"\[\[([a-zA-Z0-9_-]+)\]\]", text):
            if target not in dirs:
                dangling.add(f"{name} -> [[{target}]]")
    if dangling:
        return False, f"unresolved links: {sorted(dangling)}"
    return True, "all [[links]] resolve to a skill dir or known sibling"


# Documentation-completeness: confirms the canonical terminal-state vocabulary
# is present in loop-run's prose (a substring scan), not runtime enforcement that
# a loop actually reaches one of these states — that gate is loop doctor / verify-*.
def check_terminal_states(root, facts):
    text = _read(root / "skills" / "loop-run" / "SKILL.md")
    missing = [s for s in facts["terminal_states"] if s not in text]
    if missing:
        return False, f"loop-run missing terminal states: {missing}"
    return True, f"loop-run names all {len(facts['terminal_states'])} terminal states"


# Documentation-completeness for the field vocabulary: confirms the repair-record
# field names are present in loop-repair's prose (a substring scan). The second
# half IS structural — the examples/ failure_mode taxonomy scan parses example
# files and rejects any failure_mode value outside the canonical taxonomy.
def check_repair_fields(root, facts):
    text = _read(root / "skills" / "loop-repair" / "SKILL.md")
    missing = [f for f in facts["repair_record_fields"] if f not in text]
    if missing:
        return False, f"loop-repair missing repair-record fields: {missing}"
    taxonomy = set(facts["failure_mode_taxonomy"])
    bad = _scan_failure_modes(root / "examples", taxonomy)
    if bad:
        return False, f"non-canonical failure_mode in examples/: {bad}"
    n = len(facts["repair_record_fields"])
    return True, f"loop-repair names all {n} repair fields; example failure_modes canonical"


# Documentation-completeness: confirms the 7 eval-layer names + 2 first-class
# metrics appear in loop-evals' prose (a normalized substring scan), not runtime
# enforcement that the eval harness actually runs those layers or computes metrics.
def check_eval_layers_and_metrics(root, facts):
    ntext = _norm(_read(root / "skills" / "loop-evals" / "SKILL.md"))
    wanted = list(facts["eval_layer_names"]) + list(facts["first_class_metrics"])
    missing = [w for w in wanted if _norm(w) not in ntext]
    if missing:
        return False, f"loop-evals missing layers/metrics: {missing}"
    n_layers = len(facts["eval_layer_names"])
    n_metrics = len(facts["first_class_metrics"])
    return True, f"loop-evals covers {n_layers} layers + {n_metrics} first-class metrics"


def check_templates_present(root, facts):
    expected = facts["template_filenames"]
    have = {p.name for p in (root / "templates").glob("*")}
    missing = [t for t in expected if t not in have]
    if missing:
        return False, f"missing templates: {missing}"
    return True, f"all {len(expected)} contract templates present"


def check_no_secrets(root, facts):
    scope = ["skills", "reference", "templates", "examples", "scripts", "evals",
             ".claude-plugin"]
    hits = []
    for p in _iter_suite_files(root, scope):
        try:
            text = _read(p)
        except (UnicodeDecodeError, OSError):
            continue
        for label, rx in SECRET_PATTERNS.items():
            if rx.search(text):
                hits.append(f"{p.relative_to(root)}:{label}")
    if hits:
        return False, f"possible secrets: {hits}"
    return True, "no secret-shaped literals found"


def check_dispatch_names_model(root, facts):
    scope = ["skills", "reference", "templates", "examples"]
    offenders = []
    n_dispatch_fences = 0
    for p in _iter_suite_files(root, scope):
        text = _read(p)
        for fence in _FENCE_RE.findall(text):
            if not _DISPATCH_RE.search(fence):
                continue
            n_dispatch_fences += 1
            if "model:" not in fence and "model=" not in fence:
                offenders.append(str(p.relative_to(root)))
    if offenders:
        return False, f"agent-dispatch fence without 'model:': {sorted(set(offenders))}"
    return True, (f"all {n_dispatch_fences} agent-dispatch fences name model: "
                  "(routing contract)")


def check_license_present(root, facts):
    """Release blocker: a real MIT LICENSE file at repo root (not just a
    plugin.json/README declaration). Verifies title, holder, year, and a
    distinctive MIT body phrase so a stub file does not pass."""
    spec = facts["license"]
    path = root / "LICENSE"
    if not path.exists():
        return False, "LICENSE file missing at repo root"
    text = _read(path)
    missing = [
        label
        for label, needle in (
            ("title", spec["title"]),
            ("holder", spec["holder"]),
            ("year", spec["year"]),
            ("body", spec["body_marker"]),
        )
        if needle not in text
    ]
    if missing:
        return False, f"LICENSE present but missing {missing}"
    return True, f"LICENSE present ({spec['spdx']}, {spec['holder']} {spec['year']})"


def check_readme_differentiation(root, facts):
    """Release blocker (SPEC North Star): the README must position the suite
    against alternatives. Requires a 'How it compares' heading AND the two
    first-class metrics named, so the section is substantive, not a stub."""
    spec = facts["readme_differentiation"]
    path = root / "README.md"
    if not path.exists():
        return False, "README.md missing"
    text = _read(path)
    if not re.search(spec["section_heading_pattern"], text,
                     re.IGNORECASE | re.MULTILINE):
        return False, "README has no differentiation section heading"
    missing = [m for m in spec["required_markers"] if m not in text]
    if missing:
        return False, f"README differentiation missing markers: {missing}"
    return True, "README has differentiation section + first-class-metric markers"


def check_byo_default(root, facts):
    """Out-of-the-box invariant: a public user has none of the author's private
    tooling, so no skill may *depend* on an unbundled integration. Any SKILL.md
    that names an external-only tool (``/verify-slice``, ``.gsd/`` receipts, the
    routing hooks) must also name the bundled default path (``verify-fast``/
    ``verify-full``, the ``loop`` CLI, ``.loop/receipts``) so the skill still
    works standalone. External tools may appear only as optional integrations."""
    spec = facts["byo_default"]
    external = spec["external_tokens"]
    bundled = spec["bundled_tokens"]
    offenders = []
    for name, text in _skill_texts(root).items():
        if any(tok in text for tok in external) and not any(tok in text for tok in bundled):
            offenders.append(name)
    if offenders:
        return False, f"skills depend on an unbundled tool with no bundled default: {sorted(offenders)}"
    return True, "every skill naming an optional integration also ships the bundled default"


CHECKS = [
    ("all-skills-present", check_all_skills_present),
    ("frontmatter-valid", check_frontmatter_valid),
    ("references-used", check_references_used),
    ("links-resolve", check_links_resolve),
    ("terminal-states-documented", check_terminal_states),
    ("repair-record-fields-documented", check_repair_fields),
    ("eval-layers-and-metrics-documented", check_eval_layers_and_metrics),
    ("templates-present", check_templates_present),
    ("no-secrets", check_no_secrets),
    ("dispatch-names-model", check_dispatch_names_model),
    ("license-present", check_license_present),
    ("readme-differentiation", check_readme_differentiation),
    ("byo-default", check_byo_default),
]


def run_checks(root) -> dict:
    root = pathlib.Path(root)
    facts = _load_facts(root)
    results = []
    for name, fn in CHECKS:
        try:
            ok, detail = fn(root, facts)
        except Exception as exc:  # a broken check is a failed check, never a crash
            ok, detail = False, f"check raised {type(exc).__name__}: {exc}"
        results.append({"name": name, "ok": bool(ok), "detail": detail})
    passed_count = sum(1 for c in results if c["ok"])
    return {
        "checks": results,
        "structural_pass_rate": passed_count / len(results),
        "passed": passed_count == len(results),
    }


def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent
    report = run_checks(root)
    width = max(len(c["name"]) for c in report["checks"])
    print("loop-engineer structural self-eval")
    print("-" * (width + 9))
    for c in report["checks"]:
        mark = "PASS" if c["ok"] else "FAIL"
        print(f"  [{mark}] {c['name']:<{width}}  {c['detail']}")
    print("-" * (width + 9))
    pct = report["structural_pass_rate"] * 100
    n_ok = sum(1 for c in report["checks"] if c["ok"])
    print(f"structural_pass_rate: {report['structural_pass_rate']:.3f} "
          f"({n_ok}/{len(report['checks'])} = {pct:.0f}%)")
    print(f"passed: {report['passed']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
