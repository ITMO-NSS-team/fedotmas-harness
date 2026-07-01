"""_addressing: the single source for compiler-minted identifiers. The probe is the fixed point
mint -> parse -> base, so the flow compiler and serialize.from_blueprint cannot drift."""

from fedotmas._addressing import Branch, Loop, alias, base_of, build_id


def test_build_id_and_base_roundtrip():
    name = build_id("double", 3)
    assert name == "double#3"
    assert base_of(name) == "double"


def test_base_of_without_counter_is_identity():
    assert base_of("score") == "score"  # a rule carries no build counter


def test_loop_names_and_parse():
    ln = Loop("loop#1")
    assert (ln.iter, ln.done, ln.state) == ("loop#1:iter", "loop#1:done", "loop#1:s")
    assert (ln.body_in, ln.body_out) == ("loop#1:in", "loop#1:out")
    assert Loop.of(ln.iter).base == "loop#1"
    assert Loop.of(ln.done).base == "loop#1"


def test_branch_names_and_parse():
    bn = Branch("branch#1")
    assert bn.route == "branch#1:route"
    assert bn.inlet("x") == "branch#1:in:x"
    assert bn.join("y") == "branch#1:join:y"
    assert Branch.of(bn.route).base == "branch#1"


def test_alias():
    assert alias("out") == "alias:out"
