"""A small toolkit on top of python-docx for a plain black-and-white university report.

Everything is black on white. Headings are numbered by hand ("09. Introduction", "9.1 Background"). The table of contents, the
list of figures and the list of tables are real Word fields whose result is already filled in (so they show page numbers
without any update step); Word can still refresh them.
"""

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Emu, Pt, RGBColor

FONT = "Times New Roman"
MONO = "Courier New"
BLACK = RGBColor(0, 0, 0)
BODY_PT = 11
PAGE_W_CM = 21.0
TEXT_W_CM = 15.6  # A4 21.0 minus left 3.0 and right 2.4


def roman(n: int) -> str:
    vals = [(10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
    out = ""
    for v, s in vals:
        while n >= v:
            out += s
            n -= v
    return out


def _set_font(style_or_run, name=FONT, size=None, bold=None, italic=None):
    f = style_or_run.font
    f.name = name
    f.color.rgb = BLACK
    if size is not None:
        f.size = Pt(size)
    if bold is not None:
        f.bold = bold
    if italic is not None:
        f.italic = italic
    el = getattr(style_or_run, "element", None)
    if el is None or not hasattr(el, "get_or_add_rPr"):
        el = getattr(style_or_run, "_r", None) if hasattr(style_or_run, "_r") else style_or_run._element
    rpr = el.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(attr), name)
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme"):
        if rfonts.get(qn(attr)) is not None:
            del rfonts.attrib[qn(attr)]


def _border(el, sides, sz=4, val="single"):
    pr = el.get_or_add_tcPr() if hasattr(el, "get_or_add_tcPr") else el
    borders = pr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        pr.append(borders)
    for s in sides:
        e = OxmlElement(f"w:{s}")
        e.set(qn("w:val"), val)
        e.set(qn("w:sz"), str(sz))
        e.set(qn("w:space"), "0")
        e.set(qn("w:color"), "000000")
        borders.append(e)


@dataclass
class Entry:
    level: int
    text: str
    bookmark: str
    kind: str = "heading"  # heading | figure | table


class Report:
    def __init__(self, pages: dict | None = None):
        """pages: {bookmark: displayed page text} from a previous layout pass (None on the first pass)."""
        self.doc = Document()
        self.pages = pages or {}
        self.entries: list[Entry] = []
        self._bm = 0
        self.fig_no = 0
        self.tab_no = 0
        self._setup()

    # ------------------------------------------------------------------ setup

    def _setup(self):
        d = self.doc
        sec = d.sections[0]
        sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
        sec.left_margin, sec.right_margin = Cm(3.0), Cm(2.4)
        sec.top_margin, sec.bottom_margin = Cm(2.5), Cm(2.3)
        sec.header_distance, sec.footer_distance = Cm(1.2), Cm(1.1)
        st = d.styles
        normal = st["Normal"]
        _set_font(normal, FONT, BODY_PT)
        pf = normal.paragraph_format
        pf.space_before, pf.space_after = Pt(0), Pt(6)
        pf.line_spacing_rule, pf.line_spacing = WD_LINE_SPACING.MULTIPLE, 1.12
        pf.widow_control = True
        for name, size, before, after, italic in (("Heading 1", 16, 0, 10, False), ("Heading 2", 13, 12, 5, False), ("Heading 3", 11.5, 9, 3, True)):
            s = st[name]
            _set_font(s, FONT, size, bold=True, italic=italic)
            s.paragraph_format.space_before, s.paragraph_format.space_after = Pt(before), Pt(after)
            s.paragraph_format.keep_with_next = True
            s.paragraph_format.line_spacing = 1.05
        # a thin black rule under every main heading
        h1 = st["Heading 1"].element.get_or_add_pPr()
        pb = OxmlElement("w:pBdr")
        bt = OxmlElement("w:bottom")
        for k, v in (("val", "single"), ("sz", "8"), ("space", "3"), ("color", "000000")):
            bt.set(qn(f"w:{k}"), v)
        pb.append(bt)
        h1.append(pb)
        for name in ("List Bullet", "List Number", "List Bullet 2"):
            _set_font(st[name], FONT, BODY_PT)
            st[name].paragraph_format.space_after = Pt(3)
        cap = st["Caption"]
        _set_font(cap, FONT, 10, bold=True, italic=False)
        cap.paragraph_format.space_before, cap.paragraph_format.space_after = Pt(4), Pt(10)
        cap.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.paragraph_format.keep_together = True
        for lvl, ind in ((1, 0), (2, 0.6), (3, 1.2)):
            name = f"TOC {lvl}"
            try:
                s = st[name]
            except KeyError:
                s = st.add_style(name, 1)
                s.base_style = normal
            _set_font(s, FONT, 11 if lvl == 1 else 10.5, bold=(lvl == 1))
            s.paragraph_format.left_indent = Cm(ind)
            s.paragraph_format.space_after = Pt(2 if lvl > 1 else 3)
            s.paragraph_format.space_before = Pt(5 if lvl == 1 else 0)
            s.paragraph_format.line_spacing = 1.0
        try:
            tof = st["Table of Figures"]
        except KeyError:
            tof = st.add_style("Table of Figures", 1)
            tof.base_style = normal
        _set_font(tof, FONT, 10.5)
        tof.paragraph_format.space_after = Pt(2)
        tof.paragraph_format.line_spacing = 1.0
        # document properties
        d.core_properties.title = "ShopSathi: Final Project Report"
        d.core_properties.author = "ShopSathi project team"
        d.core_properties.subject = "AI sales agent for small online shops in Bangladesh"
        # settings: no colour themes, do not ask to update fields
        # footer / header are built per section
        self._first_section = True

    # ------------------------------------------------------------------ low level

    def _bookmark(self, paragraph, name):
        self._bm += 1
        s = OxmlElement("w:bookmarkStart")
        s.set(qn("w:id"), str(self._bm))
        s.set(qn("w:name"), name)
        e = OxmlElement("w:bookmarkEnd")
        e.set(qn("w:id"), str(self._bm))
        paragraph._p.insert(1 if paragraph._p.pPr is not None else 0, s)
        paragraph._p.append(e)

    @staticmethod
    def _fld(paragraph, instr, result="1", bold=None, size=None):
        def run_with(child):
            r = paragraph.add_run()
            if bold is not None:
                r.font.bold = bold
            if size:
                r.font.size = Pt(size)
            r._r.append(child)
            return r

        b = OxmlElement("w:fldChar")
        b.set(qn("w:fldCharType"), "begin")
        run_with(b)
        it = OxmlElement("w:instrText")
        it.set(qn("xml:space"), "preserve")
        it.text = f" {instr} "
        run_with(it)
        sp = OxmlElement("w:fldChar")
        sp.set(qn("w:fldCharType"), "separate")
        run_with(sp)
        r = paragraph.add_run(result)
        if bold is not None:
            r.font.bold = bold
        if size:
            r.font.size = Pt(size)
        en = OxmlElement("w:fldChar")
        en.set(qn("w:fldCharType"), "end")
        run_with(en)

    def _runs(self, p, text, size=None, bold=None, italic=None, mono=False):
        """Text with **bold**, *italic* and `code` markers."""
        for part in re.split(r"(\*\*[^*]+\*\*|`[^`]+`|(?<!\*)\*[^*\s][^*]*\*(?!\*))", text):
            if not part:
                continue
            if part.startswith("**") and part.endswith("**"):
                r = p.add_run(part[2:-2])
                r.bold = True
            elif part.startswith("`") and part.endswith("`"):
                r = p.add_run(part[1:-1])
                _set_font(r, MONO, (size or BODY_PT) - 1.5)
            elif part.startswith("*") and part.endswith("*") and len(part) > 2:
                r = p.add_run(part[1:-1])
                r.italic = True
            else:
                r = p.add_run(part)
                if bold:
                    r.bold = True
            if size and not (part.startswith("`")):
                r.font.size = Pt(size)
            if italic:
                r.italic = True
            if mono:
                _set_font(r, MONO, (size or BODY_PT) - 1.5)
        return p

    # ------------------------------------------------------------------ text blocks

    def h1(self, text, page_break=True, bookmark=None):
        p = self.doc.add_paragraph(style="Heading 1")
        if getattr(self, "_skip_break", False):
            page_break = False
            self._skip_break = False
        if page_break:
            p.paragraph_format.page_break_before = True
        p.add_run(text)
        bm = bookmark or f"_Toc{len(self.entries) + 1000}"
        self._bookmark(p, bm)
        self.entries.append(Entry(1, text, bm))
        return p

    def mark(self, paragraph, text, level=1):
        """Put a contents entry on an existing paragraph (used for the cover page)."""
        bm = f"_Toc{len(self.entries) + 1000}"
        self._bookmark(paragraph, bm)
        self.entries.append(Entry(level, text, bm))

    def h2(self, text):
        p = self.doc.add_paragraph(style="Heading 2")
        p.add_run(text)
        bm = f"_Toc{len(self.entries) + 1000}"
        self._bookmark(p, bm)
        self.entries.append(Entry(2, text, bm))
        return p

    def h3(self, text):
        p = self.doc.add_paragraph(style="Heading 3")
        p.add_run(text)
        return p

    def p(self, text, align=None, size=None, italic=None, space_after=None, keep_next=False):
        p = self.doc.add_paragraph()
        self._runs(p, text, size=size, italic=italic)
        if align == "center":
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if space_after is not None:
            p.paragraph_format.space_after = Pt(space_after)
        if keep_next:
            p.paragraph_format.keep_with_next = True
        return p

    def bullets(self, items, style="List Bullet"):
        for it in items:
            p = self.doc.add_paragraph(style=style)
            self._runs(p, it)
        return self

    def numbered(self, items):
        for i, it in enumerate(items, 1):
            p = self.doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.9)
            p.paragraph_format.first_line_indent = Cm(-0.6)
            p.paragraph_format.space_after = Pt(3)
            self._runs(p, f"{i}.  {it}")

    def code(self, text, size=8.5):
        """A boxed block of monospaced text."""
        t = self.doc.add_table(rows=1, cols=1)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        c = t.rows[0].cells[0]
        c.width = Cm(TEXT_W_CM)
        self._table_borders(t)
        first = True
        for line in text.strip("\n").split("\n"):
            p = c.paragraphs[0] if first else c.add_paragraph()
            first = False
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.0
            r = p.add_run(line if line else " ")
            _set_font(r, MONO, size)
        self._cant_split(t)
        self.doc.add_paragraph().paragraph_format.space_after = Pt(4)

    # ------------------------------------------------------------------ tables

    def _table_borders(self, table, header=False):
        tbl = table._tbl
        pr = tbl.tblPr
        b = OxmlElement("w:tblBorders")
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
            e = OxmlElement(f"w:{side}")
            e.set(qn("w:val"), "single")
            e.set(qn("w:sz"), "4")
            e.set(qn("w:space"), "0")
            e.set(qn("w:color"), "000000")
            b.append(e)
        pr.append(b)
        lay = OxmlElement("w:tblLayout")
        lay.set(qn("w:type"), "fixed")
        pr.append(lay)
        cm = OxmlElement("w:tblCellMar")
        for side, w in (("top", 40), ("left", 80), ("bottom", 40), ("right", 80)):
            e = OxmlElement(f"w:{side}")
            e.set(qn("w:w"), str(w))
            e.set(qn("w:type"), "dxa")
            cm.append(e)
        pr.append(cm)

    @staticmethod
    def _cant_split(table):
        for row in table.rows:
            trpr = row._tr.get_or_add_trPr()
            e = OxmlElement("w:cantSplit")
            trpr.append(e)

    def caption_table(self, title):
        self.tab_no += 1
        p = self.doc.add_paragraph(style="Caption")
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(4)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run("Table ")
        self._fld(p, "SEQ Table \\* ARABIC", str(self.tab_no), bold=True, size=10)
        p.add_run(f": {title}")
        bm = f"_Tab{self.tab_no}"
        self._bookmark(p, bm)
        self.entries.append(Entry(1, f"Table {self.tab_no}: {title}", bm, "table"))

    def table(self, header, rows, widths, title, size=9, align=None, bold_first_col=False):
        """widths in cm (sum <= 15.6). `align`: list of 'l'/'c'/'r' per column."""
        self.caption_table(title)
        t = self.doc.add_table(rows=1, cols=len(header))
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        self._table_borders(t)
        total = sum(widths)
        if total > TEXT_W_CM + 0.05:
            widths = [w * TEXT_W_CM / total for w in widths]
        grid = t._tbl.tblGrid
        for gc, w in zip(grid.findall(qn("w:gridCol")), widths):
            gc.set(qn("w:w"), str(int(w * 567)))
        for i, h in enumerate(header):
            c = t.rows[0].cells[i]
            c.width = Cm(widths[i])
            p = c.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.0
            r = p.add_run(h)
            _set_font(r, FONT, size, bold=True)
            _border(c._tc, ["bottom"], sz=12, val="double")
        trpr = t.rows[0]._tr.get_or_add_trPr()
        th = OxmlElement("w:tblHeader")
        trpr.append(th)
        for row in rows:
            cells = t.add_row().cells
            for i, val in enumerate(row):
                c = cells[i]
                c.width = Cm(widths[i])
                lines = str(val).split("\n")
                for j, line in enumerate(lines):
                    p = c.paragraphs[0] if j == 0 else c.add_paragraph()
                    p.paragraph_format.space_after = Pt(0)
                    p.paragraph_format.line_spacing = 1.0
                    if align and align[i] == "c":
                        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    elif align and align[i] == "r":
                        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    self._runs(p, line, size=size, bold=(bold_first_col and i == 0))
        self._cant_split(t)
        sp = self.doc.add_paragraph()
        sp.paragraph_format.space_after = Pt(4)
        sp.paragraph_format.line_spacing = 0.6
        return t

    def kv_table(self, rows, title, widths=(4.2, 11.4), size=9.5):
        """A two-column table: label | text (used for use case descriptions)."""
        self.caption_table(title)
        t = self.doc.add_table(rows=0, cols=2)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        self._table_borders(t)
        grid = t._tbl.tblGrid
        for gc, w in zip(grid.findall(qn("w:gridCol")), widths):
            gc.set(qn("w:w"), str(int(w * 567)))
        for k, v in rows:
            cells = t.add_row().cells
            cells[0].width, cells[1].width = Cm(widths[0]), Cm(widths[1])
            p = cells[0].paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(k)
            _set_font(r, FONT, size, bold=True)
            lines = str(v).split("\n")
            for j, line in enumerate(lines):
                p = cells[1].paragraphs[0] if j == 0 else cells[1].add_paragraph()
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.0
                self._runs(p, line, size=size)
        self._cant_split(t)
        sp = self.doc.add_paragraph()
        sp.paragraph_format.space_after = Pt(4)
        sp.paragraph_format.line_spacing = 0.6

    # ------------------------------------------------------------------ figures

    def figure(self, image_path, title, width_cm=15.0, note=None):
        self.fig_no += 1
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(2)
        from PIL import Image

        with Image.open(image_path) as im:
            w, h = im.size
        width_cm = min(width_cm, TEXT_W_CM)
        height_cm = width_cm * h / w
        max_h = 21.0
        if height_cm > max_h:
            width_cm *= max_h / height_cm
        p.add_run().add_picture(str(image_path), width=Cm(width_cm))
        cp = self.doc.add_paragraph(style="Caption")
        cp.add_run("Figure ")
        self._fld(cp, "SEQ Figure \\* ARABIC", str(self.fig_no), bold=True, size=10)
        cp.add_run(f": {title}")
        bm = f"_Fig{self.fig_no}"
        self._bookmark(cp, bm)
        self.entries.append(Entry(1, f"Figure {self.fig_no}: {title}", bm, "figure"))
        if note:
            self.p(note)
        return self.fig_no

    # ------------------------------------------------------------------ sections / headers

    def new_section(self, number_fmt="decimal", start=1, header_text="ShopSathi: Final Project Report", first_page_blank=False, link=False):
        if self._first_section:
            sec = self.doc.sections[0]
            self._first_section = False
        else:
            sec = self.doc.add_section(WD_SECTION.NEW_PAGE)
        self._skip_break = True
        sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
        sec.left_margin, sec.right_margin = Cm(3.0), Cm(2.4)
        sec.top_margin, sec.bottom_margin = Cm(2.5), Cm(2.3)
        sec.header.is_linked_to_previous = False
        sec.footer.is_linked_to_previous = False
        sec.different_first_page_header_footer = first_page_blank
        pg = sec._sectPr.find(qn("w:pgNumType"))
        if pg is None:
            pg = OxmlElement("w:pgNumType")
            sec._sectPr.append(pg)
        pg.set(qn("w:fmt"), number_fmt)
        pg.set(qn("w:start"), str(start))
        if not first_page_blank:
            self._header_footer(sec, header_text)
        else:
            for part in (sec.header, sec.footer):
                part.paragraphs[0].text = ""
            sec.first_page_header.paragraphs[0].text = ""
            sec.first_page_footer.paragraphs[0].text = ""
        return sec

    def _header_footer(self, sec, header_text):
        hp = sec.header.paragraphs[0]
        hp.text = ""
        r = hp.add_run(header_text)
        _set_font(r, FONT, 9, italic=True)
        hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        ppr = hp._p.get_or_add_pPr()
        pb = OxmlElement("w:pBdr")
        bt = OxmlElement("w:bottom")
        for k, v in (("val", "single"), ("sz", "4"), ("space", "2"), ("color", "000000")):
            bt.set(qn(f"w:{k}"), v)
        pb.append(bt)
        ppr.append(pb)
        fp = sec.footer.paragraphs[0]
        fp.text = ""
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self._fld(fp, "PAGE", "1", size=10)

    # ------------------------------------------------------------------ the fields with a ready result

    def _toc_block(self, instr, entries, level_style):
        """entries: list of (level, text, bookmark). One field spanning all entry paragraphs."""
        first = True
        paras = []
        for i, (lvl, text, bm) in enumerate(entries):
            p = self.doc.add_paragraph(style=level_style(lvl))
            paras.append(p)
            pf = p.paragraph_format
            pf.tab_stops.add_tab_stop(Cm(TEXT_W_CM), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            if i == 0:
                for t, val in (("begin", None), ("instr", instr), ("separate", None)):
                    r = p.add_run()
                    if t == "instr":
                        it = OxmlElement("w:instrText")
                        it.set(qn("xml:space"), "preserve")
                        it.text = f" {instr} "
                        r._r.append(it)
                    else:
                        fc = OxmlElement("w:fldChar")
                        fc.set(qn("w:fldCharType"), t)
                        r._r.append(fc)
            h = OxmlElement("w:hyperlink")
            h.set(qn("w:anchor"), bm)
            h.set(qn("w:history"), "1")
            r1 = OxmlElement("w:r")
            t1 = OxmlElement("w:t")
            t1.set(qn("xml:space"), "preserve")
            t1.text = text
            r1.append(t1)
            h.append(r1)
            r2 = OxmlElement("w:r")
            r2.append(OxmlElement("w:tab"))
            h.append(r2)
            r3 = OxmlElement("w:r")
            t3 = OxmlElement("w:t")
            t3.text = self.pages.get(bm, "0")
            r3.append(t3)
            h.append(r3)
            p._p.append(h)
        # close the field in the last paragraph
        last = paras[-1]
        r = last.add_run()
        fc = OxmlElement("w:fldChar")
        fc.set(qn("w:fldCharType"), "end")
        r._r.append(fc)

    def toc(self, placeholder_entries):
        self._toc_block('TOC \\o "1-2" \\h \\z \\u', placeholder_entries, lambda lvl: f"TOC {lvl}")

    def list_of(self, label, entries):
        self._toc_block(f'TOC \\h \\z \\c "{label}"', entries, lambda lvl: "Table of Figures")

    def page_break(self):
        self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    def _blacken_styles(self):
        """The default Word template carries coloured styles. Make every colour in the style definitions black and drop shading."""
        root = self.doc.styles.element
        for el in list(root.iter(qn("w:color"))):
            for a in ("themeColor", "themeShade", "themeTint"):
                el.attrib.pop(qn("w:" + a), None)
            el.set(qn("w:val"), "000000")
        for tag in ("w:shd",):
            for el in list(root.iter(qn(tag))):
                el.getparent().remove(el)
        for el in list(root.iter(qn("w:bdr"))) + list(root.iter(qn("w:top"))) + list(root.iter(qn("w:bottom"))) + list(root.iter(qn("w:left"))) + list(root.iter(qn("w:right"))) + list(root.iter(qn("w:insideH"))) + list(root.iter(qn("w:insideV"))):
            if el.get(qn("w:color")) not in (None, "auto", "000000"):
                for a in ("themeColor", "themeShade", "themeTint"):
                    el.attrib.pop(qn("w:" + a), None)
                el.set(qn("w:color"), "000000")

    def save(self, path):
        self._blacken_styles()
        for el in self.doc.styles.element.iter():
            for a in list(el.attrib):
                if "theme" in a.lower().split("}")[-1]:
                    del el.attrib[a]
        self.doc.save(str(path))
        self._drop_legacy_styles(path)

    @staticmethod
    def _drop_legacy_styles(path):
        """python-docx's template also ships stylesWithEffects.xml (coloured table styles). The report does not use it."""
        import re
        import shutil
        import zipfile

        tmp = str(path) + ".tmp"
        with zipfile.ZipFile(str(path)) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "word/stylesWithEffects.xml":
                    continue
                if item.filename == "word/_rels/document.xml.rels":
                    data = re.sub(rb"<Relationship [^>]*stylesWithEffects[^>]*/>", b"", data)
                if item.filename == "[Content_Types].xml":
                    data = re.sub(rb"<Override [^>]*stylesWithEffects[^>]*/>", b"", data)
                zout.writestr(item, data)
        shutil.move(tmp, str(path))
