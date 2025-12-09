from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Optional, Tuple, List
import xml.etree.ElementTree as ET
import re

# Support both ALTO v3 and v4 namespaces
NS_V3 = {"alto": "http://www.loc.gov/standards/alto/ns-v3#"}
NS_V4 = {"alto": "http://www.loc.gov/standards/alto/ns-v4#"}
NS = NS_V4  # Default to v4 for backward compatibility
HY_PHENS = ("-", "-", "—" "--")  # plain hyphen + common variants
CLEAN_RE = re.compile(r"[^A-Za-z0-9-]+")  # regex to clean non-alphanumeric chars except hyphens

def _detect_alto_version(root: ET.Element) -> dict:
	"""
	Detect ALTO version from XML root element.
	
	Returns:
		Namespace dictionary for the detected version
	"""
	# Check root namespace
	root_ns = root.tag.split('}')[0].lstrip('{') if '}' in root.tag else ''
	
	# Try to find Page element with different namespaces
	if root.find(".//{http://www.loc.gov/standards/alto/ns-v3#}Page") is not None:
		return NS_V3
	elif root.find(".//{http://www.loc.gov/standards/alto/ns-v4#}Page") is not None:
		return NS_V4
	elif 'ns-v3' in root_ns:
		return NS_V3
	elif 'ns-v4' in root_ns:
		return NS_V4
	else:
		# Default to v4, but will try both in load functions
		return NS_V4

def load_pages_from_file(path: str) -> list[Page]:
	"""
	Parse an XML file and return a Page object.
	(Assumes the root element is <Page>.)
	"""
	tree = ET.parse(path)
	root = tree.getroot()
	
	# Try both v3 and v4 namespaces
	ns = _detect_alto_version(root)
	pages = root.findall(".//alto:Page", namespaces=ns)
	if not pages:
		# Try the other namespace
		other_ns = NS_V3 if ns == NS_V4 else NS_V4
		pages = root.findall(".//alto:Page", namespaces=other_ns)
	
	return [Page.from_xml(p, ns) for p in pages]

def load_first_page(path: str) -> Page:
	tree = ET.parse(path)
	root = tree.getroot()
	
	# Try both v3 and v4 namespaces
	ns = _detect_alto_version(root)
	el = root.find(".//alto:Page", namespaces=ns)
	if el is None:
		# Try the other namespace
		other_ns = NS_V3 if ns == NS_V4 else NS_V4
		el = root.find(".//alto:Page", namespaces=other_ns)
		if el is not None:
			ns = other_ns
	
	if el is None:
		raise ValueError("No <Page> element found in ALTO file.")
	return Page.from_xml(el, ns)


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
	wc: float  # word confidence (can be float in ALTO v3)
	matched: bool = False
	before_word: Optional[StringWord] = None
	after_word: Optional[StringWord] = None
	best_clean_content: str = None

	@classmethod
	def from_xml(cls, el: ET.Element, ns: dict = None) -> "StringWord":
		if ns is None:
			ns = NS
		return cls(
			id=el.attrib.get("ID", ""),
			width=int(el.attrib.get("WIDTH", 0)),
			height=int(el.attrib.get("HEIGHT", 0)),
			hpos=int(el.attrib.get("HPOS", 0)),
			vpos=int(el.attrib.get("VPOS", 0)),
			content=el.attrib.get("CONTENT", ""),
			wc=float(el.attrib.get("WC", 0)) if '.' in el.attrib.get("WC", "0") else int(el.attrib.get("WC", 0)),
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
	def from_xml(cls, el: ET.Element, ns: dict = None) -> "TextLine":
		if ns is None:
			ns = NS
		strings = [
			StringWord.from_xml(s_el, ns)
				for s_el in el.findall("alto:String", namespaces=ns)
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
	def from_xml(cls, el: ET.Element, ns: dict = None) -> "TextBlock":
		if ns is None:
			ns = NS
		lines = [
			TextLine.from_xml(tl_el, ns)
				for tl_el in el.findall("alto:TextLine", namespaces=ns)
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
	def from_xml(cls, el: ET.Element, ns: dict = None) -> "Page":
		if ns is None:
			ns = NS
		
		# In ALTO v3, TextBlocks can be inside PrintSpace or ComposedBlock
		# In ALTO v4, TextBlocks are directly under Page
		# Try to find TextBlocks directly under Page first
		blocks = []
		text_blocks = el.findall("alto:TextBlock", namespaces=ns)
		
		if not text_blocks:
			# Try looking inside PrintSpace (ALTO v3)
			print_space = el.find("alto:PrintSpace", namespaces=ns)
			if print_space is not None:
				# TextBlocks can be directly in PrintSpace or inside ComposedBlocks
				text_blocks = print_space.findall(".//alto:TextBlock", namespaces=ns)
		
		blocks = [TextBlock.from_xml(tb_el, ns) for tb_el in text_blocks]
		
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
		return self.words[self.words.index(word) - 1]

	def get_next_word(self, word: "StringWord") -> "StringWord":
		"""
		Gets the next word of a given word.
		"""
		return self.words[self.words.index(word) + 1]

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
	
	def update_content_from_mapping(self, hypothesis_list: List) -> "Page":
		"""
		Create a new Page object with CONTENT values updated based on mapping results.
		
		This function takes a list of TokenHypotheses (from map_up_text) and creates
		a new Page object where each StringWord's content is replaced with the
		corrected text from the mapping.
		
		Args:
			hypothesis_list: List of TokenHypotheses objects with chosen_LLM_token set
			
		Returns:
			New Page object with corrected content values
			
		Note:
			- Words that were merged: all merged StringWords get the merged corrected text
			- Words that were split: each split part gets its corresponding corrected text
			- Words without a match keep their original content
		"""
		# Create a mapping from StringWord (by id) to corrected text
		# Handle both single words and merged words (where multiple StringWords map to one LLM token)
		stringword_to_corrected = {}
		for hyp in hypothesis_list:
			if hyp.chosen_LLM_token is not None:
				corrected_text = hyp.chosen_LLM_token.word
				
				# Get all StringWords that map to this hypothesis
				# For merged words, the candidate's alto_words contains all merged words
				if hyp.candidates and hyp.chosen_index is not None:
					chosen_candidate = hyp.candidates[hyp.chosen_index]
					# Use all alto_words from the chosen candidate (handles merged words)
					for alto_word in chosen_candidate.alto_words:
						stringword_to_corrected[id(alto_word)] = corrected_text
				else:
					# Fallback to just the anchor
					stringword_to_corrected[id(hyp.anchor)] = corrected_text
		
		# Create a deep copy of the page structure
		# We'll rebuild it with updated content
		new_blocks = []
		for block in self.content_elements:
			new_lines = []
			for line in block.content_elements:
				new_strings = []
				for string_word in line.content_elements:
					# Check if this word has a corrected mapping
					string_id = id(string_word)
					if string_id in stringword_to_corrected:
						# Create new StringWord with corrected content
						corrected_content = stringword_to_corrected[string_id]
						new_string = StringWord(
							id=string_word.id,
							width=string_word.width,
							height=string_word.height,
							hpos=string_word.hpos,
							vpos=string_word.vpos,
							content=corrected_content,
							wc=string_word.wc,
							matched=string_word.matched,
							before_word=string_word.before_word,
							after_word=string_word.after_word,
							best_clean_content=corrected_content
						)
					else:
						# Keep original content if no mapping found
						new_string = StringWord(
							id=string_word.id,
							width=string_word.width,
							height=string_word.height,
							hpos=string_word.hpos,
							vpos=string_word.vpos,
							content=string_word.content,
							wc=string_word.wc,
							matched=string_word.matched,
							before_word=string_word.before_word,
							after_word=string_word.after_word,
							best_clean_content=string_word.best_clean_content
						)
					new_strings.append(new_string)
				
				# Create new TextLine with updated strings
				new_line = TextLine(
					id=line.id,
					width=line.width,
					height=line.height,
					hpos=line.hpos,
					vpos=line.vpos,
					content_elements=new_strings
				)
				new_lines.append(new_line)
			
			# Create new TextBlock with updated lines
			new_block = TextBlock(
				id=block.id,
				width=block.width,
				height=block.height,
				hpos=block.hpos,
				vpos=block.vpos,
				content_elements=new_lines
			)
			new_blocks.append(new_block)
		
		# Create new Page with updated blocks
		new_page = Page(
			id=self.id,
			width=self.width,
			height=self.height,
			physical_img_nr=self.physical_img_nr,
			content_elements=new_blocks
		)
		
		return new_page
	
	def save_corrected_xml(self, hypothesis_list: List, output_path: str) -> str:
		"""
		Create a corrected XML file with updated content values and save it.
		
		Args:
			hypothesis_list: List of TokenHypotheses objects with chosen_LLM_token set
			output_path: Path to save the corrected XML file
			
		Returns:
			Path to the saved XML file
		"""
		import os
		import xml.etree.ElementTree as ET
		
		# Get corrected page
		corrected_page = self.update_content_from_mapping(hypothesis_list)
		
		# Convert to XML
		page_el = corrected_page.to_xml()
		
		# Create root element with ALTO namespace
		root = ET.Element("alto", {
			"xmlns": "http://www.loc.gov/standards/alto/ns-v4#",
			"xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
			"xsi:schemaLocation": "http://www.loc.gov/standards/alto/ns-v4# http://www.loc.gov/standards/alto/v4/alto-4-3.xsd"
		})
		
		# Create Description and Layout elements (minimal structure)
		description = ET.SubElement(root, "Description")
		measurement_unit = ET.SubElement(description, "MeasurementUnit")
		measurement_unit.text = "pixel"
		
		layout = ET.SubElement(root, "Layout")
		page_el.set("ID", corrected_page.id)
		page_el.set("WIDTH", str(corrected_page.width))
		page_el.set("HEIGHT", str(corrected_page.height))
		page_el.set("PHYSICAL_IMG_NR", str(corrected_page.physical_img_nr))
		layout.append(page_el)
		
		# Create tree and write to file
		tree = ET.ElementTree(root)
		ET.indent(tree, space="  ")  # Pretty print (Python 3.9+)
		
		os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
		tree.write(output_path, encoding='utf-8', xml_declaration=True)
		
		return output_path

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