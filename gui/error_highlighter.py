"""
Error highlighting module for GUI.

Provides functionality to highlight errors on images and handle
manual word corrections.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QMessageBox
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRect
from PyQt6.QtGui import QPainter, QColor, QPen, QPixmap, QImage
from PIL import Image, ImageDraw
from PIL.ImageQt import ImageQt
from typing import List, Optional, Tuple, Dict

from map_up_text import TokenHypotheses
import xml_obj as XMLOBJ
import text_utils


class ErrorHighlighter(QWidget):
    """Widget that displays image with error highlights and handles click-to-fix."""
    
    word_corrected = pyqtSignal(object, str)  # Emits (hypothesis, new_text)
    words_merged = pyqtSignal(list, str)  # Emits (list of hypotheses, merged_text)
    word_split = pyqtSignal(object, list)  # Emits (hypothesis, list of split_texts)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = None
        self.hypothesis_list = None
        self.page = None
        self.error_rects = []  # List of (rect, hypothesis) tuples
        self.selected_hypotheses = []  # List of selected hypotheses (for merge/split)
        self.init_ui()
    
    def init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        
        # Image display label
        self.image_label = QLabel("No image loaded")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(400, 300)
        self.image_label.setStyleSheet("border: 1px solid gray;")
        self.image_label.mousePressEvent = self.on_image_click
        layout.addWidget(self.image_label)
        
        # Selection info
        self.selection_label = QLabel("No selection")
        layout.addWidget(self.selection_label)
        
        # Correction input (for single word correction)
        correction_group = QWidget()
        correction_layout = QHBoxLayout(correction_group)
        
        correction_layout.addWidget(QLabel("Corrected word:"))
        self.correction_input = QLineEdit()
        self.correction_input.setEnabled(False)
        self.correction_input.returnPressed.connect(self.update_word)  # Enter to update
        correction_layout.addWidget(self.correction_input)
        
        self.update_btn = QPushButton("Update Word")
        self.update_btn.setEnabled(False)
        self.update_btn.clicked.connect(self.update_word)
        correction_layout.addWidget(self.update_btn)
        
        layout.addWidget(correction_group)
        
        # Merge/Split controls
        merge_split_group = QWidget()
        merge_split_layout = QHBoxLayout(merge_split_group)
        
        merge_split_layout.addWidget(QLabel("Merge/Split:"))
        
        self.merge_input = QLineEdit()
        self.merge_input.setPlaceholderText("Enter merged word...")
        self.merge_input.setEnabled(False)
        self.merge_input.returnPressed.connect(self.merge_words)
        merge_split_layout.addWidget(self.merge_input)
        
        self.merge_btn = QPushButton("Merge Selected")
        self.merge_btn.setEnabled(False)
        self.merge_btn.clicked.connect(self.merge_words)
        merge_split_layout.addWidget(self.merge_btn)
        
        self.split_input = QLineEdit()
        self.split_input.setPlaceholderText("Enter split words (space-separated)...")
        self.split_input.setEnabled(False)
        self.split_input.returnPressed.connect(self.split_word)
        merge_split_layout.addWidget(self.split_input)
        
        self.split_btn = QPushButton("Split Selected")
        self.split_btn.setEnabled(False)
        self.split_btn.clicked.connect(self.split_word)
        merge_split_layout.addWidget(self.split_btn)
        
        self.clear_selection_btn = QPushButton("Clear Selection")
        self.clear_selection_btn.setEnabled(False)
        self.clear_selection_btn.clicked.connect(self.clear_selection)
        merge_split_layout.addWidget(self.clear_selection_btn)
        
        layout.addWidget(merge_split_group)
    
    def load_image_and_errors(self, image_path: str, hypothesis_list: List[TokenHypotheses],
                             page: XMLOBJ.Page):
        """Load image and highlight errors."""
        try:
            self.image = Image.open(image_path)
            self.hypothesis_list = hypothesis_list
            self.page = page
            self.selected_hypotheses = []  # Reset selection
            
            # Create highlighted image
            highlighted_image = self.create_highlighted_image()
            
            # Display
            max_size = 800
            display_img = highlighted_image.copy()
            if max(display_img.size) > max_size:
                display_img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            
            pixmap = QPixmap.fromImage(ImageQt(display_img))
            self.image_label.setPixmap(pixmap)
            self.image_label.setScaledContents(False)
            
            # Store scale factor for click mapping
            self.scale_factor = max_size / max(self.image.size) if max(self.image.size) > max_size else 1.0
            
            # Update UI
            self.update_selection_ui()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load image: {str(e)}")
    
    def create_highlighted_image(self) -> Image.Image:
        """Create image with error highlights."""
        if self.image is None or self.hypothesis_list is None:
            return self.image
        
        # Create copy for drawing
        img = self.image.copy()
        draw = ImageDraw.Draw(img, 'RGBA')
        
        # Calculate scale factors
        scale_x = img.width / self.page.width if self.page.width > 0 else 1.0
        scale_y = img.height / self.page.height if self.page.height > 0 else 1.0
        
        # Clear error rects
        self.error_rects = []
        
        # Create set of selected hypothesis IDs for quick lookup
        selected_ids = {id(hyp) for hyp in self.selected_hypotheses}
        
        # Draw highlights for errors and selected words
        for hyp in self.hypothesis_list:
            anchor = hyp.anchor
            
            # Calculate rectangle in image coordinates
            x = int(anchor.hpos * scale_x)
            y = int(anchor.vpos * scale_y)
            w = int(anchor.width * scale_x)
            h = int(anchor.height * scale_y)
            
            # Check if selected
            is_selected = id(hyp) in selected_ids
            
            if is_selected:
                # Draw blue highlight for selected words
                draw.rectangle([x, y, x + w, y + h], fill=(0, 0, 255, 150), outline=(0, 0, 255, 255), width=3)
            elif hyp.flagged_for_error:
                # Draw red highlight for errors
                draw.rectangle([x, y, x + w, y + h], fill=(255, 0, 0, 100), outline=(255, 0, 0, 200), width=2)
            
            # Store rect for click detection (all words, not just errors)
            self.error_rects.append((QRect(x, y, w, h), hyp))
        
        return img
    
    def on_image_click(self, event):
        """Handle click on image to select word(s). Supports multi-selection with Ctrl/Cmd."""
        if not self.error_rects or self.image is None:
            return
        
        # Get click position in image coordinates
        label_size = self.image_label.size()
        pixmap = self.image_label.pixmap()
        if pixmap is None:
            return
        
        pixmap_size = pixmap.size()
        
        # Calculate offset to center image in label
        offset_x = (label_size.width() - pixmap_size.width()) / 2
        offset_y = (label_size.height() - pixmap_size.height()) / 2
        
        # Click position relative to pixmap
        click_x = event.position().x() - offset_x
        click_y = event.position().y() - offset_y
        
        # Scale back to original image coordinates
        if pixmap_size.width() > 0 and pixmap_size.height() > 0:
            scale_x = self.image.width / pixmap_size.width()
            scale_y = self.image.height / pixmap_size.height()
            
            img_x = int(click_x * scale_x)
            img_y = int(click_y * scale_y)
            
            # Find clicked word
            for rect, hyp in self.error_rects:
                anchor = hyp.anchor
                scale_x_rect = self.image.width / self.page.width if self.page.width > 0 else 1.0
                scale_y_rect = self.image.height / self.page.height if self.page.height > 0 else 1.0
                
                rect_x = int(anchor.hpos * scale_x_rect)
                rect_y = int(anchor.vpos * scale_y_rect)
                rect_w = int(anchor.width * scale_x_rect)
                rect_h = int(anchor.height * scale_y_rect)
                
                if (rect_x <= img_x <= rect_x + rect_w and
                    rect_y <= img_y <= rect_y + rect_h):
                    # Found clicked word
                    # Check if Ctrl/Cmd is held for multi-selection
                    modifiers = event.modifiers()
                    is_multi_select = (modifiers & Qt.KeyboardModifier.ControlModifier) or \
                                     (modifiers & Qt.KeyboardModifier.MetaModifier)
                    
                    if is_multi_select:
                        # Toggle selection
                        if hyp in self.selected_hypotheses:
                            self.selected_hypotheses.remove(hyp)
                        else:
                            self.selected_hypotheses.append(hyp)
                    else:
                        # Single selection
                        self.selected_hypotheses = [hyp]
                    
                    self.update_selection_ui()
                    self.refresh_display()
                    break
    
    def update_selection_ui(self):
        """Update UI based on current selection."""
        num_selected = len(self.selected_hypotheses)
        
        if num_selected == 0:
            self.selection_label.setText("No selection")
            self.correction_input.setEnabled(False)
            self.update_btn.setEnabled(False)
            self.merge_input.setEnabled(False)
            self.merge_btn.setEnabled(False)
            self.split_input.setEnabled(False)
            self.split_btn.setEnabled(False)
            self.clear_selection_btn.setEnabled(False)
        elif num_selected == 1:
            # Single selection - enable correction
            hyp = self.selected_hypotheses[0]
            current_word = ""
            if hyp.chosen_LLM_token:
                current_word = hyp.chosen_LLM_token.word
            else:
                current_word = text_utils.decode_html_entities(hyp.anchor.content)
            
            self.selection_label.setText(f"Selected: '{current_word}' (1 word)")
            self.correction_input.setText(current_word)
            self.correction_input.setEnabled(True)
            self.update_btn.setEnabled(True)
            
            # Enable split for single selection
            self.split_input.setEnabled(True)
            self.split_btn.setEnabled(True)
            
            # Disable merge for single selection
            self.merge_input.setEnabled(False)
            self.merge_btn.setEnabled(False)
            
            self.clear_selection_btn.setEnabled(True)
        else:
            # Multiple selection - enable merge
            words = []
            for hyp in self.selected_hypotheses:
                if hyp.chosen_LLM_token:
                    words.append(hyp.chosen_LLM_token.word)
                else:
                    words.append(text_utils.decode_html_entities(hyp.anchor.content))
            
            self.selection_label.setText(f"Selected: {num_selected} words - {', '.join(words[:3])}{'...' if len(words) > 3 else ''}")
            
            # Disable single word correction
            self.correction_input.setEnabled(False)
            self.update_btn.setEnabled(False)
            
            # Enable merge for multiple selection
            self.merge_input.setEnabled(True)
            self.merge_btn.setEnabled(True)
            # Suggest merged text (concatenate selected words)
            suggested_merge = ''.join(words)
            self.merge_input.setText(suggested_merge)
            self.merge_input.selectAll()
            
            # Disable split for multiple selection
            self.split_input.setEnabled(False)
            self.split_btn.setEnabled(False)
            
            self.clear_selection_btn.setEnabled(True)
    
    def refresh_display(self):
        """Refresh the image display with updated highlights."""
        if self.image is None:
            return
        
        highlighted_image = self.create_highlighted_image()
        
        max_size = 800
        display_img = highlighted_image.copy()
        if max(display_img.size) > max_size:
            display_img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        pixmap = QPixmap.fromImage(ImageQt(display_img))
        self.image_label.setPixmap(pixmap)
    
    def clear_selection(self):
        """Clear all selections."""
        self.selected_hypotheses = []
        self.update_selection_ui()
        self.refresh_display()
    
    def update_word(self):
        """Update the selected word with correction (single word only)."""
        if len(self.selected_hypotheses) != 1:
            return
        
        hyp = self.selected_hypotheses[0]
        new_text = self.correction_input.text().strip()
        if not new_text:
            QMessageBox.warning(self, "Warning", "Please enter a correction")
            return
        
        # Emit signal to update hypothesis
        self.word_corrected.emit(hyp, new_text)
        
        # Clear selection
        self.clear_selection()
        
        QMessageBox.information(self, "Success", "Word updated. Re-run mapping to see changes.")
    
    def merge_words(self):
        """Merge multiple selected words into one."""
        if len(self.selected_hypotheses) < 2:
            QMessageBox.warning(self, "Warning", "Please select at least 2 words to merge")
            return
        
        merged_text = self.merge_input.text().strip()
        if not merged_text:
            QMessageBox.warning(self, "Warning", "Please enter the merged word")
            return
        
        # Sort hypotheses by reading order (left to right, top to bottom)
        sorted_hypotheses = sorted(
            self.selected_hypotheses,
            key=lambda h: (h.anchor.vpos, h.anchor.hpos)
        )
        
        # Emit signal to merge words
        self.words_merged.emit(sorted_hypotheses, merged_text)
        
        # Clear selection
        self.clear_selection()
        
        QMessageBox.information(self, "Success", f"Merged {len(sorted_hypotheses)} words into '{merged_text}'. Re-run mapping to see changes.")
    
    def split_word(self):
        """Split a single selected word into multiple words."""
        if len(self.selected_hypotheses) != 1:
            QMessageBox.warning(self, "Warning", "Please select exactly 1 word to split")
            return
        
        hyp = self.selected_hypotheses[0]
        split_texts = self.split_input.text().strip().split()
        
        if len(split_texts) < 2:
            QMessageBox.warning(self, "Warning", "Please enter at least 2 words separated by spaces")
            return
        
        # Emit signal to split word
        self.word_split.emit(hyp, split_texts)
        
        # Clear selection
        self.clear_selection()
        
        QMessageBox.information(self, "Success", f"Split word into {len(split_texts)} words. Re-run mapping to see changes.")


def get_word_at_position(x: int, y: int, hypothesis_list: List[TokenHypotheses],
                        page: XMLOBJ.Page) -> Optional[TokenHypotheses]:
    """
    Find word at given position.
    
    Args:
        x: X coordinate in image space
        y: Y coordinate in image space
        hypothesis_list: List of TokenHypotheses
        page: Page object with dimensions
        
    Returns:
        TokenHypotheses at position, or None
    """
    for hyp in hypothesis_list:
        anchor = hyp.anchor
        if (anchor.hpos <= x <= anchor.hpos + anchor.width and
            anchor.vpos <= y <= anchor.vpos + anchor.height):
            return hyp
    return None


def update_word_correction(hypothesis: TokenHypotheses, new_text: str,
                          llm_elements: List) -> None:
    """
    Update TokenHypotheses with manual correction.
    
    Args:
        hypothesis: TokenHypotheses to update
        new_text: New corrected text
        llm_elements: List of LLM tokens (to find or create matching token)
    """
    from map_up_text import LLMToken
    
    # Find or create matching LLM token
    matching_token = None
    for llm_token in llm_elements:
        if llm_token.word == new_text and not llm_token.matched:
            matching_token = llm_token
            break
    
    # If no matching token found, create a new one
    # (This is a simplified approach - in practice, you might want to
    #  insert it in the correct position in the sequence)
    if matching_token is None:
        matching_token = LLMToken(word=new_text, word_normalized=text_utils.normalize_for_matching(new_text))
        # Note: w_before and w_after would need to be set based on context
    
    # Update hypothesis
    hypothesis.chosen_LLM_token = matching_token
    matching_token.matched = True
    hypothesis.flagged_for_error = False
    
    # Update chosen_index if there's a matching candidate
    for i, candidate in enumerate(hypothesis.candidates):
        if candidate.clean_form == text_utils.normalize_for_matching(new_text):
            hypothesis.chosen_index = i
            break

