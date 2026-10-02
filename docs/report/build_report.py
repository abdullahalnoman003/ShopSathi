"""Builds the final report DOCX in several passes so that the contents, list of figures and list of tables carry real page numbers.

pass 1: build with a dummy contents to collect the headings, figures and tables
pass 2: build with the real entry lists (page numbers unknown), convert with LibreOffice, read the page of every entry from the PDF
pass 3: build with the page numbers, convert again, check that they did not move (repeat when they did)
"""
import re
import subprocess
import sys
from pathlib import Path

from pypdf import PdfReader

import rep_a, rep_b, rep_c, rep_d, rep_e, rep_f, rep_g
from docxkit import Report, roman

HERE = Path(__file__).parent
OUT = HERE / "out"
FINAL = HERE.parent / "ShopSathi_Final_Report.docx"
SOFFICE = r"E:\lo_dl\lo\program\soffice.exe"


def build(pages, toc, figs, tabs, path):
    r = Report(pages)
    r.new_section(first_page_blank=True)
    rep_a.cover(r)
    r.new_section("lowerRoman", 2)
    rep_a.front(r)
    rep_a.lists(r, toc, figs, tabs)
    rep_a.abbreviations(r)
    r.new_section("decimal", 1)
    rep_a.introduction(r)
    rep_a.background(r)
    rep_a.problem(r)
    rep_a.motivation(r)
    rep_a.objectives(r)
    rep_a.scope(r)
    rep_a.target_users(r)
    rep_a.existing(r)
    rep_a.existing_problems(r)
    rep_a.proposed(r)
    rep_a.stakeholders(r)
    rep_a.roles(r)
    rep_b.requirements(r)
    rep_b.traceability_table(r)
    rep_b.nonfunctional(r)
    rep_b.business_rules(r)
    rep_b.uc_diagrams(r)
    rep_b.uc_descriptions(r)
    rep_b.scenarios(r)
    rep_b.context_diagram(r)
    rep_b.flowchart(r)
    rep_b.activity_diagrams(r)
    rep_b.sequence_diagrams(r)
    rep_b.state_diagrams(r)
    rep_c.architecture(r)
    rep_c.components(r)
    rep_c.deployment(r)
    rep_c.ai_arch(r)
    rep_c.messenger_arch(r)
    rep_c.er(r)
    rep_c.schema(r)
    rep_c.relationships(r)
    rep_c.indexing(r)
    rep_c.uiux(r)
    rep_c.wireframes(r)
    rep_c.screens(r)
    rep_c.modules(r)
    rep_d.api(r)
    rep_d.ai_impl(r)
    rep_d.security(r)
    rep_d.tenancy(r)
    rep_d.rbac(r)
    rep_d.fb_security(r)
    rep_e.strategy(r)
    rep_e.unit(r)
    rep_e.integration(r)
    rep_e.api_tests(r)
    rep_e.e2e(r)
    rep_e.ai_testing(r)
    rep_e.ui_testing(r)
    rep_e.results(r)
    rep_e.performance(r)
    rep_e.nfr_eval(r)
    rep_f.deployment(r)
    rep_f.docker(r)
    rep_f.env_setup(r)
    rep_f.cicd(r)
    rep_f.monitoring(r)
    rep_f.results(r)
    rep_f.limitations(r)
    rep_f.future(r)
    rep_g.conclusion(r)
    rep_g.references(r)
    rep_g.appendix(r)
    rep_g.install(r)
    rep_g.manual(r)
    rep_g.sample_api(r)
    rep_g.sample_tests(r)
    rep_g.screenshots(r)
    r.save(path)
    return r


def split_entries(entries):
    toc = [(e.level, e.text, e.bookmark) for e in entries if e.kind == "heading"]
    figs = [(1, e.text, e.bookmark) for e in entries if e.kind == "figure"]
    tabs = [(1, e.text, e.bookmark) for e in entries if e.kind == "table"]
    return toc, figs, tabs


def to_pdf(docx):
    subprocess.run([SOFFICE, "-env:UserInstallation=file:///E:/lo_profile", "--headless", "--convert-to", "pdf", "--outdir", str(OUT), str(docx)],
                   check=True, capture_output=True, timeout=600)
    return OUT / (Path(docx).stem + ".pdf")


def norm(s):
    return re.sub(r"\s+", "", s)


def page_map(pdf, entries):
    reader = PdfReader(str(pdf))
    pages = []
    for p in reader.pages:
        txt = p.extract_text() or ""
        pages.append([norm(line) for line in txt.split("\n") if line.strip() and not re.search(r"\.{4,}", line)])
    found = {}
    for e in entries:
        key = norm(e.text)[:38]
        hit = None
        for idx, lines in enumerate(pages):
            if any(l.startswith(key) for l in lines):
                hit = idx
        if e.text.startswith("01. Cover"):
            hit = 0
        found[e.bookmark] = hit
    intro = [e for e in entries if e.text.startswith("09. Introduction")][0]
    body_start = found[intro.bookmark]
    labels = {}
    for e in entries:
        idx = found[e.bookmark]
        if idx is None:
            labels[e.bookmark] = "?"
        elif idx < body_start:
            labels[e.bookmark] = roman(idx + 1)
        else:
            labels[e.bookmark] = str(idx - body_start + 1)
    return labels, len(pages), found


def main():
    OUT.mkdir(exist_ok=True)
    tmp = OUT / "ShopSathi_Final_Report.docx"
    r = build({}, [(1, "x", "_Toc0")], [(1, "x", "_Fig0")], [(1, "x", "_Tab0")], tmp)
    toc, figs, tabs = split_entries(r.entries)
    print("entries:", len(toc), len(figs), len(tabs))
    pages = {}
    for rnd in range(4):
        r = build(pages, toc, figs, tabs, tmp)
        pdf = to_pdf(tmp)
        labels, n, found = page_map(pdf, r.entries)
        missing = [k for k, v in labels.items() if v == "?"]
        changed = sum(1 for k, v in labels.items() if pages.get(k) != v)
        print(f"round {rnd}: pdf pages {n}, missing {len(missing)}, changed {changed}")
        if missing:
            for e in r.entries:
                if e.bookmark in missing[:10]:
                    print("  missing:", e.text[:70])
        pages = labels
        if changed == 0:
            break
    FINAL.parent.mkdir(exist_ok=True)
    import shutil

    shutil.copy(tmp, FINAL)
    print("final:", FINAL)


if __name__ == "__main__":
    sys.exit(main())
