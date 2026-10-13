"""Builder parses model output, keeps house-style HTML path, and routes other formats to renderers."""

from __future__ import annotations

import pytest

from artifactsmith import builder as b


def test_parse_output_html():
    text = """===ASSUMPTIONS===
- none
===SUMMARY===
A page.
===FILE: index.html===
<html><body>ok</body></html>
===END===
"""
    assumptions, summary, body = b.parse_output(text)
    assert assumptions == []
    assert summary == "A page."
    assert "<html>" in body


def test_needs_input_block():
    text = "===NEEDS_INPUT===\nNeed the store code.\n===END===\n"
    assert "store code" in (b.needs_input(text) or "")


_HTML_PAGE = "<!DOCTYPE html><html><head><title>T</title></head><body><p>Ready</p></body></html>"


def test_finished_html_detection_reuses_document_check():
    assert b.source_has_html_document({"source_content": _HTML_PAGE})
    assert b.source_has_html_document({"source_content": "\ufeff" + _HTML_PAGE})
    assert b.source_has_html_document({"source_content": "```html\n" + _HTML_PAGE + "\n```"})
    assert b.source_has_html_document({"source_files": [{"name": "page.html", "content": _HTML_PAGE}]})
    assert not b.source_has_html_document({"source_content": "# Pilot\n\nnotes\n"})
    assert not b.source_has_html_document({"source_content": "<p>fragment</p>"})
    assert not b.source_has_html_document({"source_content": "<!-- note -->\n" + _HTML_PAGE})
    assert not b.source_has_html_document(None)
    assert b.request_wants_html_unchanged("Publish the attached HTML file exactly as-is")
    assert b.request_wants_html_unchanged("Keep the HTML page unchanged")
    assert b.request_wants_html_unchanged("Leave this HTML document as-is")
    assert b.request_wants_html_unchanged("The HTML page is unchanged")
    assert b.request_wants_html_unchanged("do not restyle the HTML page")
    assert b.request_wants_html_unchanged("do not add, remove, reword or restyle the HTML")
    assert not b.request_wants_html_unchanged("keep the numbers unchanged")
    assert not b.request_wants_html_unchanged("Build an HTML page from these notes. Keep the store code unchanged.")
    assert not b.request_wants_html_unchanged("Do not add a chart. The accent is the HTML color #c45.")
    assert not b.request_wants_html_unchanged("Summarize the HTML email. Do not remove the disclaimer.")
    assert not b.request_wants_html_unchanged("Show HTML examples but leave the prices unchanged.")
    assert not b.request_wants_html_unchanged("keep the HTML color unchanged")
    assert not b.request_wants_html_unchanged("")
    assert b.skip_fast_for_finished_html("summarize", {"source_content": _HTML_PAGE})
    assert not b.skip_fast_for_finished_html("summarize", {"source_content": "# notes\n"})


def test_fast_html_refusal_names_publish_or_full():
    produced = (
        "The requested page is an HTML document, but this artifact accepts Markdown only "
        "and cannot publish HTML, CSS, classes, attributes, or links exactly as-is."
    )
    clarified = b.clarify_fast_html_refusal(produced)
    assert "publish tool" in clarified
    assert 'mode="full"' in clarified
    assert "as-is" in clarified
    assert len(clarified) <= 500
    other = (
        "The requested page is HTML, but this artifact must be emitted as Markdown only. "
        "Please provide permission to include raw HTML."
    )
    other_out = b.clarify_fast_html_refusal(other)
    assert "publish tool" in other_out and 'mode="full"' in other_out
    assert b.clarify_fast_html_refusal("Need the store code.") == "Need the store code."
    assert b.clarify_fast_html_refusal("Need the HTML color") == "Need the HTML color"
    color = b.clarify_fast_html_refusal("Need the HTML color for the markdown section")
    assert color == "Need the HTML color for the markdown section"
    short = b.clarify_fast_html_refusal("Cannot publish HTML as-is.")
    assert "publish tool" in short and 'mode="full"' in short and "as-is" in short
    already = 'HTML accepts Markdown only. Use the publish tool, or call create with mode="full".'
    assert b.clarify_fast_html_refusal(already) == already


def test_needs_input_ignored_when_file_present():
    text = "===FILE: index.html===\n<html></html>\n===NEEDS_INPUT===\nnope\n"
    assert b.needs_input(text) is None


def test_render_html_wrapper():
    files, primary = b.render_html("<html><body>x</body></html>")
    assert primary == "index.html"
    assert files[primary].startswith(b"<html>")


@pytest.mark.asyncio
async def test_run_build_html(monkeypatch):
    async def fake_call(model, system, user, timeout=300):
        assert "===FILE: index.html===" in system
        return (
            "===ASSUMPTIONS===\n- none\n===SUMMARY===\npage\n"
            "===FILE: index.html===\n<html><body>HARBOR-17</body></html>\n===END===\n"
        )

    monkeypatch.setattr(b.llm, "call", fake_call)
    notes = []
    res = await b.run_build(
        kind="web_static",
        slug="s",
        display_name="Pilot",
        verbatim="show code",
        model="test-model",
        base_source=None,
        base_version=None,
        history=[],
        progress=notes.append,
        source={"source_content": "The pilot store code is HARBOR-17."},
        format="html",
    )
    assert res.primary == "index.html"
    assert b"HARBOR-17" in res.files["index.html"]


@pytest.mark.asyncio
async def test_run_build_pdf(monkeypatch):
    async def fake_call(model, system, user, timeout=300):
        assert "===FILE: content.md===" in system
        return (
            "===ASSUMPTIONS===\n- none\n===SUMMARY===\ndoc\n"
            "===FILE: content.md===\n# Pilot\n\nThe code is HARBOR-17.\n===END===\n"
        )

    monkeypatch.setattr(b.llm, "call", fake_call)
    res = await b.run_build(
        kind="web_static",
        slug="s",
        display_name="Pilot",
        verbatim="show code",
        model="test-model",
        base_source=None,
        base_version=None,
        history=[],
        progress=lambda _m: None,
        format="pdf",
    )
    assert res.primary == "document.pdf"
    assert res.files["document.pdf"].startswith(b"%PDF")
    assert b"HARBOR-17" in res.files["content.md"]


@pytest.mark.asyncio
async def test_run_build_rejects_secret(monkeypatch):
    async def fake_call(model, system, user, timeout=300):
        return (
            "===ASSUMPTIONS===\n- none\n===SUMMARY===\nbad\n"
            "===FILE: content.md===\n# x\n\nsk-" + ("b" * 24) + "\n===END===\n"
        )

    monkeypatch.setattr(b.llm, "call", fake_call)
    with pytest.raises(b.BuildError, match="secret"):
        await b.run_build(
            kind="web_static",
            slug="s",
            display_name="x",
            verbatim="x",
            model="test-model",
            base_source=None,
            base_version=None,
            history=[],
            progress=lambda _m: None,
            format="markdown",
        )


@pytest.mark.asyncio
async def test_run_build_rejects_secret_in_title(monkeypatch):
    async def fake_call(model, system, user, timeout=300):
        return (
            "===ASSUMPTIONS===\n- none\n===SUMMARY===\nok\n"
            "===FILE: content.md===\n# clean\n\nno secrets here\n===END===\n"
        )

    monkeypatch.setattr(b.llm, "call", fake_call)
    with pytest.raises(b.BuildError, match="secret"):
        await b.run_build(
            kind="web_static",
            slug="s",
            display_name="sk-" + ("c" * 24),
            verbatim="x",
            model="test-model",
            base_source=None,
            base_version=None,
            history=[],
            progress=lambda _m: None,
            format="markdown",
        )


@pytest.mark.asyncio
async def test_run_build_needs_input(monkeypatch):
    async def fake_call(model, system, user, timeout=300):
        return "===NEEDS_INPUT===\nNeed revenue.\n===END===\n"

    monkeypatch.setattr(b.llm, "call", fake_call)
    with pytest.raises(b.NeedsInput, match="revenue"):
        await b.run_build(
            kind="web_static",
            slug="s",
            display_name="x",
            verbatim="x",
            model="test-model",
            base_source=None,
            base_version=None,
            history=[],
            progress=lambda _m: None,
            format="html",
        )


def test_needs_input_inline():
    assert "store" in (b.needs_input("NEEDS_INPUT: store code") or "")


def test_parse_output_errors_and_fence():
    with pytest.raises(b.BuildError, match="section markers"):
        b.parse_output("no markers here")
    with pytest.raises(b.BuildError, match="no FILE"):
        b.parse_output("===ASSUMPTIONS===\n- none\n===END===\n")
    assumptions, summary, body = b.parse_output(
        "```html\n===ASSUMPTIONS===\n- none\n===SUMMARY===\nok\n"
        "===FILE: index.html===\n```html\n<html></html>\n```\n===END===\n```"
    )
    assert "html" in body
    assert summary == "ok"
    assert assumptions == []


def test_source_block_and_edit_prompt():
    empty = b.source_block(None)
    assert "none supplied" in empty
    filled = b.source_block({"source_content": "code is X", "source_files": [{"name": "notes.txt", "content": "more"}]})
    assert "code is X" in filled and "notes.txt" in filled
    assert "attached file" in filled
    assert "attached file" not in empty
    prompt = b.build_user_prompt("change it", "Pilot", "<html/>", 1, ["first"], {"source_content": "n"})
    assert "EDIT of version 1" in prompt
    assert b.system_prompt_for("html") == b.SYSTEM
    assert "Markdown" in b.system_prompt_for("pdf")
    assert b.sha256(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


@pytest.mark.asyncio
async def test_run_build_retries_then_fails(monkeypatch):
    async def fake_call(model, system, user, timeout=300):
        return "not a valid builder reply"

    monkeypatch.setattr(b.llm, "call", fake_call)
    with pytest.raises(b.BuildError, match="failed checks twice"):
        await b.run_build(
            kind="web_static",
            slug="s",
            display_name="x",
            verbatim="x",
            model="gpt-test",
            base_source=None,
            base_version=None,
            history=[],
            progress=lambda _m: None,
            format="html",
        )


@pytest.mark.asyncio
async def test_run_build_rejects_unknown_format():
    with pytest.raises(b.BuildError, match="unsupported"):
        await b.run_build(
            kind="web_static",
            slug="s",
            display_name="x",
            verbatim="x",
            model="gpt-test",
            base_source=None,
            base_version=None,
            history=[],
            progress=lambda _m: None,
            format="rtf",
        )
