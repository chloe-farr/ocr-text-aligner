"""
Pipeline controller module for orchestrating the OCR pipeline stages.

Manages stage transitions, state, and execution flow with user approval checkpoints.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple
import os

# Import pipeline modules
import image_preprocessing
import tesseract_ocr
import llm_cleaning
import pdf_generation
import map_up_text
import xml_obj as XMLOBJ


class PipelineStage(Enum):
    """Pipeline stage enumeration."""
    IMAGE_PREP = "image_prep"
    OCR = "ocr"
    LLM_CLEAN = "llm_clean"
    MAPPING = "mapping"
    PDF_GEN = "pdf_gen"
    COMPLETE = "complete"


@dataclass
class PipelineState:
    """State container for pipeline execution."""
    # Inputs
    image_path: Optional[str] = None
    image: Optional[Any] = None  # PIL Image
    
    # Image prep
    image_prep_config: Dict[str, Any] = field(default_factory=dict)
    
    # OCR outputs
    ocr_xml_path: Optional[str] = None
    ocr_plaintext_path: Optional[str] = None
    ocr_hocr_path: Optional[str] = None
    ocr_language: str = "eng"
    ocr_config: Dict[str, Any] = field(default_factory=dict)
    
    # LLM outputs
    clean_text_path: Optional[str] = None
    clean_text: Optional[str] = None
    llm_model: str = "qwen2.5"
    llm_context: Optional[str] = None
    
    # Mapping outputs
    hypothesis_list: Optional[List] = None
    page: Optional[XMLOBJ.Page] = None
    mapping_output_dir: Optional[str] = None
    
    # PDF output
    pdf_path: Optional[str] = None
    
    # Current stage
    current_stage: PipelineStage = PipelineStage.IMAGE_PREP
    
    # Output directory
    output_dir: str = "outputs"


class PipelineController:
    """Controller for managing pipeline execution."""
    
    def __init__(self, output_dir: str = "outputs"):
        """
        Initialize pipeline controller.
        
        Args:
            output_dir: Base directory for all outputs
        """
        self.state = PipelineState(output_dir=output_dir)
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def set_image(self, image_path: str, prep_config: Optional[Dict[str, Any]] = None):
        """
        Set input image and prepare it.
        
        Args:
            image_path: Path to input image
            prep_config: Optional image preprocessing configuration
        """
        self.state.image_path = image_path
        
        # Load the image directly (it's already preprocessed if coming from GUI)
        from PIL import Image
        self.state.image = Image.open(image_path)
        
        # Convert to RGB if necessary
        if self.state.image.mode != 'RGB':
            self.state.image = self.state.image.convert('RGB')
        
        if prep_config is None:
            prep_config = {}
        
        self.state.image_prep_config = prep_config
        self.state.current_stage = PipelineStage.IMAGE_PREP
    
    def run_ocr(self, language: str = "eng", config_options: Optional[Dict[str, Any]] = None,
               generate_pdf: bool = False) -> Dict[str, str]:
        """
        Run Tesseract OCR stage.
        
        Args:
            language: Tesseract language code
            config_options: Optional Tesseract config options
            generate_pdf: Whether to generate PDF from Tesseract
            
        Returns:
            Dictionary of output file paths
        """
        if self.state.image is None:
            raise ValueError("Image must be set before running OCR")
        
        if config_options is None:
            config_options = {}
        
        self.state.ocr_language = language
        self.state.ocr_config = config_options
        
        # Generate base name from image path
        base_name = os.path.splitext(os.path.basename(self.state.image_path))[0]
        ocr_output_dir = os.path.join(self.output_dir, base_name)
        
        # Save the image that will be used for OCR to a visible location
        # This helps users debug cropping/preprocessing issues
        ocr_input_image_path = os.path.join(ocr_output_dir, f"{base_name}_input_to_ocr.png")
        os.makedirs(ocr_output_dir, exist_ok=True)
        # Save a copy of the image that will be used for OCR
        ocr_image = self.state.image.copy()  # Make a copy to avoid modifying the original
        if ocr_image.mode != 'RGB':
            ocr_image = ocr_image.convert('RGB')
        ocr_image.save(ocr_input_image_path)
        self.state.ocr_input_image_path = ocr_input_image_path
        
        # Run OCR
        results = tesseract_ocr.run_full_ocr(
            self.state.image,
            ocr_output_dir,
            base_name,
            language,
            config_options,
            generate_pdf
        )
        
        self.state.ocr_xml_path = results['xml']
        self.state.ocr_plaintext_path = results['plaintext']
        self.state.ocr_hocr_path = results['hocr']
        self.state.current_stage = PipelineStage.OCR
        
        return results
    
    def run_llm_cleaning(self, model: str = "qwen2.5", 
                        user_context: Optional[str] = None,
                        system_prompt: Optional[str] = None,
                        base_url: str = "http://localhost:11434") -> str:
        """
        Run LLM text cleaning stage.
        
        Args:
            model: LLM model name
            user_context: Optional contextual information
            system_prompt: Optional custom system prompt
            base_url: Ollama API base URL
            
        Returns:
            Path to cleaned text file
        """
        if self.state.ocr_plaintext_path is None:
            raise ValueError("OCR must be run before LLM cleaning")
        
        self.state.llm_model = model
        self.state.llm_context = user_context
        
        # Generate output path
        base_name = os.path.splitext(os.path.basename(self.state.ocr_plaintext_path))[0]
        base_name = base_name.replace('_plaintext', '')
        clean_text_path = os.path.join(
            os.path.dirname(self.state.ocr_plaintext_path),
            f"{base_name}_cleantext.txt"
        )
        
        # Run LLM cleaning
        llm_cleaning.clean_text_file(
            self.state.ocr_plaintext_path,
            clean_text_path,
            model,
            system_prompt,
            user_context,
            base_url
        )
        
        # Read cleaned text
        with open(clean_text_path, 'r', encoding='utf-8') as f:
            self.state.clean_text = f.read()
        
        self.state.clean_text_path = clean_text_path
        self.state.current_stage = PipelineStage.LLM_CLEAN
        
        return clean_text_path
    
    def run_mapping(self, show_ocr_accuracy: bool = False) -> Tuple[List, XMLOBJ.Page]:
        """
        Run text mapping stage using existing map_up_text logic.
        
        Args:
            show_ocr_accuracy: Whether to show OCR accuracy analysis
            
        Returns:
            Tuple of (hypothesis_list, page)
        """
        if self.state.ocr_xml_path is None:
            raise ValueError("OCR XML must be generated before mapping")
        if self.state.clean_text is None:
            raise ValueError("Clean text must be generated before mapping")
        
        # Import mapping functions
        from map_up_text import (
            create_LLM_element_list,
            create_hypothesis_list,
            run_candidate_pipeline,
            run_iterative_pipeline,
            analyze_ocr_accuracy,
            link_hypothesis_objects_by_context,
            assign_llm_candidates_to_all_token_hypotheses_by_fuzzy_matching,
            _rerun_context_matching_pipeline
        )
        import paragraph_reordering
        import weak_fuzzy_matching
        import visualize_matching as viz
        
        # Verify XML file exists and is valid
        if not os.path.exists(self.state.ocr_xml_path):
            raise ValueError(f"OCR XML file not found: {self.state.ocr_xml_path}")
        
        # Load page from XML with better error handling
        try:
            page = XMLOBJ.load_first_page(self.state.ocr_xml_path)
        except ValueError as e:
            # Provide more helpful error message with file path
            error_msg = (
                f"Failed to load XML file: {str(e)}\n\n"
                f"XML file path: {self.state.ocr_xml_path}\n"
                f"File exists: {os.path.exists(self.state.ocr_xml_path)}\n\n"
                "Please ensure the XML file is a valid ALTO XML file with a <Page> element.\n"
                "The file should have been generated by Tesseract OCR."
            )
            raise ValueError(error_msg) from e
        except Exception as e:
            # Catch any other XML parsing errors
            error_msg = (
                f"Error parsing XML file '{self.state.ocr_xml_path}': {str(e)}\n\n"
                f"Please verify the XML file is valid and was generated correctly by Tesseract."
            )
            raise ValueError(error_msg) from e
        
        self.state.page = page
        
        # Create LLM elements
        llm_elements = create_LLM_element_list(self.state.clean_text)
        
        # Create vocabulary
        from collections import Counter
        clean_vocab_counter = Counter(e.word_normalized for e in llm_elements)
        clean_vocab = set(clean_vocab_counter.keys())
        
        # Get ALTO words
        alto_words = page.all_strings()
        page.set_word_triplets(alto_words)
        
        # Create hypothesis list
        hypothesis_list = create_hypothesis_list(alto_words, clean_vocab)
        
        # Analyze OCR accuracy
        analyze_ocr_accuracy(hypothesis_list, show=show_ocr_accuracy)
        
        # Extract test page name for output
        xml_path_parts = self.state.ocr_xml_path.replace("\\", "/").split("/")
        if len(xml_path_parts) >= 2 and xml_path_parts[0] == "input":
            testpagename = xml_path_parts[1]
        else:
            testpagename = os.path.splitext(os.path.basename(self.state.ocr_xml_path))[0]
        
        output_dir = os.path.join(self.output_dir, testpagename)
        os.makedirs(output_dir, exist_ok=True)
        self.state.mapping_output_dir = output_dir
        
        # Create visualization of original OCR
        viz.visualize_original_ocr_text(
            hypothesis_list,
            page,
            self.state.ocr_xml_path,
            output_dir=output_dir
        )
        
        # Run candidate pipeline
        hypothesis_list = run_candidate_pipeline(hypothesis_list, llm_elements)
        
        # Run iterative pipeline
        hypothesis_list = run_iterative_pipeline(hypothesis_list, llm_elements, page, max_iterations=5)
        
        # Re-run context matching
        hypothesis_list = link_hypothesis_objects_by_context(hypothesis_list)
        hypothesis_list = assign_llm_candidates_to_all_token_hypotheses_by_fuzzy_matching(hypothesis_list, llm_elements)
        hypothesis_list = _rerun_context_matching_pipeline(hypothesis_list, llm_elements)
        
        # Cross-boundary matching
        hypothesis_list = paragraph_reordering.reorder_paragraphs(
            hypothesis_list, llm_elements, page
        )
        
        # Re-run context matching after cross-boundary
        hypothesis_list = link_hypothesis_objects_by_context(hypothesis_list)
        hypothesis_list = assign_llm_candidates_to_all_token_hypotheses_by_fuzzy_matching(hypothesis_list, llm_elements)
        hypothesis_list = _rerun_context_matching_pipeline(hypothesis_list, llm_elements)
        
        # Weak fuzzy matching
        hypothesis_list = weak_fuzzy_matching.match_weak_fuzzy_words(
            hypothesis_list, llm_elements, page
        )
        
        # Final matching pass
        from map_up_text import find_best_candidates_for_all_hypothesis_objects
        hypothesis_list = find_best_candidates_for_all_hypothesis_objects(hypothesis_list, llm_elements)
        hypothesis_list = link_hypothesis_objects_by_context(hypothesis_list)
        
        # Final pass for PENDING words
        for hyp in hypothesis_list:
            if hyp.chosen_LLM_token is None and hyp.candidates:
                for candidate in hyp.candidates:
                    for llm_token in candidate.possible_llm_elements_by_fuzzy_match:
                        if not llm_token.matched:
                            hyp.chosen_LLM_token = llm_token
                            llm_token.matched = True
                            if candidate in hyp.candidates:
                                hyp.chosen_index = hyp.candidates.index(candidate)
                            hyp.flagged_for_error = False
                            break
                    if hyp.chosen_LLM_token:
                        break
        
        # Create visualization of cleaned text
        original_alto_content_by_id = {}
        for alto_word in alto_words:
            import text_utils
            original_alto_content_by_id[id(alto_word)] = text_utils.decode_html_entities(alto_word.content)
        
        viz.visualize_cleaned_text_positions(
            hypothesis_list,
            page,
            testpagename,
            output_dir=output_dir,
            original_alto_content_by_id=original_alto_content_by_id
        )
        
        self.state.hypothesis_list = hypothesis_list
        self.state.current_stage = PipelineStage.MAPPING
        
        return hypothesis_list, page
    
    def generate_pdf(self, output_path: Optional[str] = None) -> str:
        """
        Generate searchable PDF with corrected text.
        
        Args:
            output_path: Optional custom output path
            
        Returns:
            Path to generated PDF
        """
        if self.state.hypothesis_list is None or self.state.page is None:
            raise ValueError("Mapping must be run before PDF generation")
        if self.state.image_path is None:
            raise ValueError("Image path must be set")
        
        if output_path is None:
            base_name = os.path.splitext(os.path.basename(self.state.image_path))[0]
            output_path = os.path.join(self.state.mapping_output_dir or self.output_dir, 
                                     f"{base_name}_corrected.pdf")
        
        pdf_generation.create_searchable_pdf(
            self.state.image_path,
            self.state.hypothesis_list,
            self.state.page,
            output_path
        )
        
        self.state.pdf_path = output_path
        self.state.current_stage = PipelineStage.COMPLETE
        
        return output_path
    
    def run_full_pipeline(self, config: Dict[str, Any], 
                         approvals: Optional[Dict[PipelineStage, bool]] = None) -> PipelineState:
        """
        Run full pipeline with optional approval checkpoints.
        
        Args:
            config: Configuration dictionary with pipeline settings
            approvals: Optional dictionary mapping stages to approval status
                      If None, assumes all stages are approved
        
        Returns:
            Final pipeline state
        """
        if approvals is None:
            approvals = {stage: True for stage in PipelineStage}
        
        # Image prep
        if approvals.get(PipelineStage.IMAGE_PREP, True):
            self.set_image(config.get('image_path'), config.get('image_prep_config'))
        
        # OCR
        if approvals.get(PipelineStage.OCR, True):
            self.run_ocr(
                config.get('ocr_language', 'eng'),
                config.get('ocr_config'),
                config.get('generate_tesseract_pdf', False)
            )
        
        # LLM cleaning
        if approvals.get(PipelineStage.LLM_CLEAN, True):
            self.run_llm_cleaning(
                config.get('llm_model', 'qwen2.5'),
                config.get('llm_context'),
                config.get('llm_system_prompt'),
                config.get('ollama_base_url', 'http://localhost:11434')
            )
        
        # Mapping
        if approvals.get(PipelineStage.MAPPING, True):
            self.run_mapping(config.get('show_ocr_accuracy', False))
        
        # PDF generation
        if approvals.get(PipelineStage.PDF_GEN, True):
            self.generate_pdf(config.get('pdf_output_path'))
        
        return self.state

