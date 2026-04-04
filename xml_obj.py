from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Optional, Tuple, List
import xml.etree.ElementTree as ET
import re

# ALTO v4 (and v3) namespaces; Tesseract outputs v3
NS = {"alto": "http://www.loc.gov/standards/alto/ns-v4#", "alto3": "http://www.loc.gov/standards/alto/ns-v3#"}
HY_PHENS = ("-", "-", "—" "--")  # plain hyphen + common variants
CLEAN_RE = re.compile(r"[^A-Za-z0-9-]+")  # regex to clean non-alphanumeric chars except hyphens


def _ns(el: ET.Element) -> dict:
	"""Return a namespace dict for find/findall using this element's namespace (supports v3 and v4 ALTO)."""
	uri = ""
	if el.tag.startswith("{"):
		uri = el.tag[1 : el.tag.index("}")]
	if not uri:
		uri = "http://www.loc.gov/standards/alto/ns-v4#"
	return {"al": uri}


def load_pages_from_file(path: str) -> list[Page]:
	"""
	Parse an XML file and return a list of Page objects.
	Supports ALTO v3 (e.g. Tesseract) and v4.
	"""
	tree = ET.parse(path)
	root = tree.getroot()
	pages = root.findall(".//alto:Page", namespaces=NS) or root.findall(".//alto3:Page", namespaces=NS)
	return [Page.from_xml(p) for p in pages]


def load_first_page(path: str) -> Page:
	tree = ET.parse(path)
	root = tree.getroot()
	el = root.find(".//alto:Page", namespaces=NS) or root.find(".//alto3:Page", namespaces=NS)
	if el is None:
		raise ValueError("No <Page> element found in ALTO file.")
	return Page.from_xml(el)


# ---------- Base classes ----------

@dataclass
class XMLObj:
	"""Base for all objects with id/width/height."""
	id: str
	width: int
	height: int


@dataclass
class ContentElement(XMLObj):
	"""Base for positioned content."""
	hpos: int
	vpos: int


# ---------- Leaf element: String (word) ----------

@dataclass
class StringWord(ContentElement):
	content: str
	wc: int  # word confidence
	matched: bool = False
	before_word: Optional[StringWord] = None
	after_word: Optional[StringWord] = None
	best_clean_content: Optional[str] = None
	page_id: Optional[str] = None  # set after load; not part of String ID

	@classmethod
	def from_xml(cls, el: ET.Element) -> "StringWord":
		raw_wc = el.attrib.get("WC", "0")
		try:
			val = float(raw_wc)
			wc = int(round(val * 100)) if val <= 1.0 else int(val)  # v3: 0–1 float; v4: 0–100 int
		except (ValueError, TypeError):
			wc = 0
		return cls(
			id=el.attrib.get("ID", ""),
			width=int(el.attrib.get("WIDTH", 0)),
			height=int(el.attrib.get("HEIGHT", 0)),
			hpos=int(el.attrib.get("HPOS", 0)),
			vpos=int(el.attrib.get("VPOS", 0)),
			content=el.attrib.get("CONTENT", ""),
			wc=wc,
		)

	def to_xml(self) -> ET.Element:
		el = ET.Element("String")
		el.set("ID", self.id)
		el.set("WIDTH", str(self.width))
		el.set("HEIGHT", str(self.height))
		el.set("HPOS", str(self.hpos))
		el.set("VPOS", str(self.vpos))
		el.set("CONTENT", self.content)
		el.set("WC", str(self.wc))
		return el

	def identify_partial_words(self, next_word:StringWord, all_words:list):
		# TODO: Implement partial word identification
		pass


# ---------- TextLine ----------

@dataclass
class TextLine(ContentElement):
	content_elements: List[StringWord] = field(default_factory=list)

	@classmethod
	def from_xml(cls, el: ET.Element) -> "TextLine":
		ns = _ns(el)
		strings = [
			StringWord.from_xml(s_el)
				for s_el in el.findall("al:String", namespaces=ns)
		]
		return cls(
			id=el.attrib.get("ID", ""),
			width=int(el.attrib.get("WIDTH", 0)),
			height=int(el.attrib.get("HEIGHT", 0)),
			hpos=int(el.attrib.get("HPOS", 0)),
			vpos=int(el.attrib.get("VPOS", 0)),
			content_elements=strings,
		)

	def to_xml(self) -> ET.Element:
		el = ET.Element("TextLine")
		el.set("ID", self.id)
		el.set("WIDTH", str(self.width))
		el.set("HEIGHT", str(self.height))
		el.set("HPOS", str(self.hpos))
		el.set("VPOS", str(self.vpos))
		for s in self.content_elements:
			el.append(s.to_xml())
		return el


# ---------- TextBlock ----------

@dataclass
class TextBlock(ContentElement):
	content_elements: List[TextLine] = field(default_factory=list)

	@classmethod
	def from_xml(cls, el: ET.Element) -> "TextBlock":
		ns = _ns(el)
		lines = [
			TextLine.from_xml(tl_el)
				for tl_el in el.findall("al:TextLine", namespaces=ns)
		]
		return cls(
			id=el.attrib.get("ID", ""),
			width=int(el.attrib.get("WIDTH", 0)),
			height=int(el.attrib.get("HEIGHT", 0)),
			hpos=int(el.attrib.get("HPOS", 0)),
			vpos=int(el.attrib.get("VPOS", 0)),
			content_elements=lines,
		)

	def to_xml(self) -> ET.Element:
		el = ET.Element("TextBlock")
		el.set("ID", self.id)
		el.set("WIDTH", str(self.width))
		el.set("HEIGHT", str(self.height))
		el.set("HPOS", str(self.hpos))
		el.set("VPOS", str(self.vpos))
		for tl in self.content_elements:
			el.append(tl.to_xml())
		return el


# ---------- Page ----------

@dataclass
class Page(XMLObj):
	physical_img_nr: int
	content_elements: List[TextBlock] = field(default_factory=list)

	@classmethod
	def from_xml(cls, el: ET.Element) -> "Page":
		ns = _ns(el)
		# v3 ALTO has Page > PrintSpace > ComposedBlock > TextBlock; v4 can have direct TextBlock. Use .// to get descendants.
		blocks = [
			TextBlock.from_xml(tb_el)
				for tb_el in el.findall(".//al:TextBlock", namespaces=ns)
		]
		return cls(
			id=el.attrib.get("ID", ""),
			width=int(el.attrib.get("WIDTH", 0)),
			height=int(el.attrib.get("HEIGHT", 0)),
			physical_img_nr=int(el.attrib.get("PHYSICAL_IMG_NR", 0)),
			content_elements=blocks,
		)

	def to_xml(self) -> ET.Element:
		el = ET.Element("Page")
		el.set("ID", self.id)
		el.set("WIDTH", str(self.width))
		el.set("HEIGHT", str(self.height))
		el.set("PHYSICAL_IMG_NR", str(self.physical_img_nr))
		for tb in self.content_elements:
			el.append(tb.to_xml())
		return el

	# Example: compute functions on the collection
	def all_strings(self) -> List[StringWord]:
		"""Flatten all StringWord objects on this page."""
		return [
			s
			for block in self.content_elements
			for line in block.content_elements
			for s in line.content_elements
		]

	def set_string_page_ids(self) -> None:
		"""Set page_id on every StringWord on this page (for writer grouping)."""
		for s in self.all_strings():
			s.page_id = self.id

	
	def get_text(self, sep: str = " ") -> str:
		"""
		Concatenate CONTENT from all strings, in document order.
		"""
		text = sep.join(s.content for s in self.all_strings())
		print(text)
		return text


	def find_words(self, text: str) -> list:
		"""
		Return a list of StringWord objects whose content matches `text`.
		"""
		results = []

		for block in self.content_elements:
			for line in block.content_elements:
				for word in line.content_elements:
					if text.lower() in word.content.lower() or (word.content.lower().endswith(HY_PHENS) and CLEAN_RE.sub("", word.content.lower()) in text.lower()):
						results.append(word)

		return results


	def print_word_searched(self, word: str):
		words = page.find_words(word)

		for w in words:
			print(w.hpos, w.vpos, w.width, w.height, w.content, w.wc)
			print("\n\n")

	def set_word_triplets(self, words: List["StringWord"]) -> None:
		"""
		Sets the before_word and after_word of a given word.
		"""
		for i, word in enumerate(words):
			if i > 0:
				word.before_word = words[i - 1]
			if i < len(words) - 1:
				word.after_word = words[i + 1]

	def iter_words(self) -> Iterator["StringWord"]:
		"""
		Yield all words on the page in reading order.
		"""
		for block in self.content_elements:
			for line in block.content_elements:
				for word in line.content_elements:
					yield word

	def find_words_with_neighbors(self, text: str) -> List[Tuple[Optional["StringWord"], "StringWord", Optional["StringWord"]]]:
		"""
		For each word whose content matches `text`, return a tuple:
			(previous_word, current_word, next_word)
		where previous_word/next_word may be None at boundaries.
		"""
		words = list(self.iter_words())
		results = []

		for i, w in enumerate(words):
			if text.lower() in w.content.lower() or ("-" in w.content.lower() and CLEAN_RE.sub("", w.content.lower()) in text.lower()):
				prev_w = words[i - 1] if i > 0 else None
				next_w = words[i + 1] if i + 1 < len(words) else None
				results.append((prev_w, w, next_w))

		print(results)
		return results
						

	def get_previous_word(self, word: "StringWord") -> "StringWord":
		"""
		Gets the previous word of a given word.
		"""
		return self.all_strings()[self.all_strings().index(word) - 1]

	def get_next_word(self, word: "StringWord") -> "StringWord":
		"""
		Gets the next word of a given word.
		"""
		return self.all_strings()[self.all_strings().index(word) + 1]

	def get_word_triplets(self, word: "StringWord") -> List[Tuple[Optional["StringWord"], "StringWord", Optional["StringWord"]]]:
		"""
		Gets the neighbors of a given word.
		"""
		results = []
		words = list(self.iter_words())
		i = words.index(word)
		if i > 0:
			prev_w = words[i - 1]
			results.append((prev_w.content, word.content, None))
		if i + 1 < len(words):
			next_w = words[i + 1]
			results.append((None, word.content, next_w.content))
		if i > 0 and i + 1 < len(words):
			prev_w = words[i - 1]
			next_w = words[i + 1]
			results.append((prev_w.content, word.content, next_w.content))
		return results

# ---------- Example usage ----------

if __name__ == "__main__":
	# xml_snippet = """
	# <Page ID="PAGE_001" WIDTH="4424" HEIGHT="6105" PHYSICAL_IMG_NR="1">
	# 	<TextBlock ID="BLOCK_036" HPOS="586" VPOS="1025" WIDTH="2784" HEIGHT="177">
	# 		<TextLine ID="LINE_036_001" HPOS="586" VPOS="1025" WIDTH="2784" HEIGHT="177">
	# 			<String ID="WORD_036_001_001" HPOS="586" VPOS="1025" WIDTH="602" HEIGHT="170" CONTENT="Witness:" WC="96"/>
	# 			<String ID="WORD_036_001_002" HPOS="1219" VPOS="1046" WIDTH="468" HEIGHT="156" CONTENT="Hanoi" WC="95"/>
	# 			<String ID="WORD_036_001_003" HPOS="1720" VPOS="1026" WIDTH="450" HEIGHT="169" CONTENT="Heart" WC="96"/>
	# 			<String ID="WORD_036_001_004" HPOS="2195" VPOS="1027" WIDTH="377" HEIGHT="164" CONTENT="Raid" WC="96"/>
	# 			<String ID="WORD_036_001_005" HPOS="2622" VPOS="1058" WIDTH="219" HEIGHT="131" CONTENT="‘No" WC="96"/>
	# 			<String ID="WORD_036_001_006" HPOS="2876" VPOS="1042" WIDTH="494" HEIGHT="148" CONTENT="Error’" WC="95"/>
	# 		</TextLine>
	# 	</TextBlock>
	# </Page>
	# """
	# pages = load_pages_from_file("page-1alto-Maclear.xml")
	# page = pages[0]

	page = load_first_page("page-1alto-Maclear.xml")
	print(page.id)             # PAGE_001
	print(page.width)          # 4424
	print(page.height)         # 6105

	# root = ET.fromstring(xml_snippet)
	# page = Page.from_xml(root)

	# Now you can compute on the collection:
	# print(page.get_text())  # "Witness: Hanoi Heart Raid ‘No Error’"

	all_words = page.all_strings()
	page.set_word_triplets(all_words)
	# print("Total words on page:", len(all_words))

	# words = page.find_words("Hanoi")
	# for w in words:
	#     print(w.hpos, w.vpos, w.content, w.wc)
	

	# And recreate XML:
	# recreated_el = page.to_xml()
	# recreated_str = ET.tostring(recreated_el, encoding="unicode")
	# print(recreated_str)
	words = page.find_words("Hanoi")
	print(f"length of words:{len(words)}")
	for w in words:
		print(w)

	# page.print_word_searched("British")
	# for w in page.all_strings():
	# 	print(repr(w.content))
	print("\n --- TRIPLES---\n")
	triples = page.find_words_with_neighbors("Hanoi")

	# for prev_w, w, next_w in triples:
	# 	print("CURRENT:", w.content, w.hpos, w.vpos)
	# 	if prev_w:
	# 		print("  BEFORE:", prev_w.content)
	# 	if next_w:
	# 		print("  AFTER :", next_w.content)