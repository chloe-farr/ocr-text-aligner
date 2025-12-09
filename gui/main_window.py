"""
Main window for OCR pipeline GUI.

Provides the main application window with image viewer, text display,
and stage navigation.
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QToolBar, QStatusBar, QLabel, QPushButton, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QPoint
from PyQt6.QtGui import QAction, QIcon, QPixmap, QWheelEvent
from PIL import Image
from PIL.ImageQt import ImageQt
import os

from pipeline_controller import PipelineController, PipelineStage
from gui.stage_widgets import (
    ImagePrepWidget, ImagePrepControlsWidget, OCRReviewWidget, LLMCleaningWidget,
    MappingReviewWidget, PDFGenerationWidget
)


class MainWindow(QMainWindow):
    """Main application window."""
    
    # Signals
    stage_changed = pyqtSignal(PipelineStage)
    image_loaded = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.controller = PipelineController()
        self.current_stage = PipelineStage.IMAGE_PREP
        self.image_path = None
        self.stage_widgets = {}  # Store stage widgets
        self.open_action = None  # Will be set in create_toolbar
        
        self.init_ui()
        self.setup_stage_widgets()
        
        # Ensure open action is enabled after everything is set up
        if self.open_action:
            self.open_action.setEnabled(True)
    
    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("OCR Text Aligner")
        self.setGeometry(100, 100, 1400, 900)
        
        # Create central widget with splitter
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        
        # Create toolbar
        self.create_toolbar()
        
        # Create splitter for left (image) and right (text) panes
        # Horizontal orientation = horizontal splitter handle = left/right panes
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)
        
        # Left pane: Image viewer (will be set by stage widgets)
        self.image_widget = QWidget()
        self.image_layout = QVBoxLayout(self.image_widget)
        splitter.addWidget(self.image_widget)
        
        # Right pane: Text display (will be set by stage widgets)
        self.text_widget = QWidget()
        self.text_layout = QVBoxLayout(self.text_widget)
        splitter.addWidget(self.text_widget)
        
        # Set splitter proportions (60% image, 40% text)
        splitter.setSizes([600, 400])
        
        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
        
        # Placeholder labels (will be replaced by stage widgets)
        self.image_label = QLabel("No image loaded")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(400, 300)
        self.image_layout.addWidget(self.image_label)
        
        self.text_label = QLabel("No text to display")
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.text_layout.addWidget(self.text_label)
    
    def create_toolbar(self):
        """Create the main toolbar."""
        # Check if toolbar already exists to avoid duplicates
        existing_toolbars = self.findChildren(QToolBar)
        if existing_toolbars:
            # Remove existing toolbars
            for tb in existing_toolbars:
                self.removeToolBar(tb)
                tb.deleteLater()
        
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setMovable(False)  # Prevent toolbar from being moved
        self.addToolBar(toolbar)
        
        # File operations
        self.open_action = QAction("Open Image", self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.triggered.connect(self.open_image)
        self.open_action.setEnabled(True)  # Explicitly enable
        toolbar.addAction(self.open_action)
        
        toolbar.addSeparator()
        
        # Stage navigation buttons
        self.stage_buttons = {}
        
        stages = [
            (PipelineStage.IMAGE_PREP, "Image Prep"),
            (PipelineStage.OCR, "OCR"),
            (PipelineStage.LLM_CLEAN, "LLM Clean"),
            (PipelineStage.MAPPING, "Mapping"),
            (PipelineStage.PDF_GEN, "PDF Gen")
        ]
        
        for stage, label in stages:
            btn = QPushButton(label)
            btn.setEnabled(False)
            btn.clicked.connect(lambda checked, s=stage: self.navigate_to_stage(s))
            self.stage_buttons[stage] = btn
            toolbar.addWidget(btn)
        
        toolbar.addSeparator()
        
        # Save action
        save_action = QAction("Save", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_current)
        toolbar.addAction(save_action)
    
    def open_image(self):
        """Open an image file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Image",
            "",
            "Image Files (*.png *.jpg *.jpeg *.tiff *.tif *.bmp);;All Files (*)"
        )
        
        if file_path:
            self.load_image(file_path)
    
    def load_image(self, image_path: str):
        """Load an image into the viewer."""
        try:
            self.image_path = image_path
            self.controller.set_image(image_path)
            
            # Load image into image prep widget if it exists
            if hasattr(self, 'image_prep_widget'):
                self.image_prep_widget.load_image(image_path)
            
            # Also display in placeholder if image prep widget not shown
            if not hasattr(self, 'image_prep_widget') or self.current_stage != PipelineStage.IMAGE_PREP:
                img = Image.open(image_path)
                # Resize for display if too large
                max_size = 800
                if max(img.size) > max_size:
                    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                
                pixmap = QPixmap.fromImage(ImageQt(img))
                self.image_label.setPixmap(pixmap)
                self.image_label.setScaledContents(False)
            
            # Enable image prep stage
            self.stage_buttons[PipelineStage.IMAGE_PREP].setEnabled(True)
            
            self.status_bar.showMessage(f"Loaded: {os.path.basename(image_path)}")
            self.image_loaded.emit(image_path)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load image: {str(e)}")
    
    def setup_stage_widgets(self):
        """Set up stage widgets and connect signals."""
        # Create stage widgets
        self.image_prep_widget = ImagePrepWidget(self.controller, self)
        self.image_prep_controls_widget = ImagePrepControlsWidget(self.image_prep_widget, self.controller, self)
        self.image_prep_widget.set_controls_widget(self.image_prep_controls_widget)
        self.image_prep_controls_widget.proceed_signal.connect(self.on_image_prep_proceed)
        
        # Create OCR widget
        self.ocr_review_widget = OCRReviewWidget(self.controller, self)
        self.ocr_review_widget.approve_signal.connect(self.on_ocr_approve)
        self.ocr_review_widget.reject_signal.connect(self.on_ocr_reject)
        
        # Connect stage change signal
        self.stage_changed.connect(self.on_stage_changed)
        
        # Show initial stage
        self.on_stage_changed(PipelineStage.IMAGE_PREP)
    
    def on_stage_changed(self, stage: PipelineStage):
        """Handle stage change."""
        self.current_stage = stage
        
        if stage == PipelineStage.IMAGE_PREP:
            # Show image prep widget in left pane (image display)
            # Check if widget still exists, recreate if needed
            if not hasattr(self, 'image_prep_widget') or self.image_prep_widget is None:
                self.image_prep_widget = ImagePrepWidget(self.controller, self)
                self.image_prep_controls_widget = ImagePrepControlsWidget(self.image_prep_widget, self.controller, self)
                self.image_prep_widget.set_controls_widget(self.image_prep_controls_widget)
                self.image_prep_controls_widget.proceed_signal.connect(self.on_image_prep_proceed)
            
            self.set_image_widget(self.image_prep_widget)
            # Show controls in right pane
            self.set_text_widget(self.image_prep_controls_widget)
            
            # Load image - prefer preprocessed image if it exists, otherwise original
            image_to_load = None
            if hasattr(self, 'preprocessed_image_path') and self.preprocessed_image_path and os.path.exists(self.preprocessed_image_path):
                # Load the preprocessed image if it exists (allows re-editing after OCR)
                image_to_load = self.preprocessed_image_path
            elif self.controller.state.image_path and os.path.exists(self.controller.state.image_path):
                # Use the image from controller state (could be preprocessed or original)
                image_to_load = self.controller.state.image_path
            elif self.image_path:
                # Fall back to original image path
                image_to_load = self.image_path
            
            if image_to_load:
                self.image_prep_widget.load_image(image_to_load)
        
        elif stage == PipelineStage.OCR:
            # Show image in left pane with scroll area for full image display
            # Prefer the OCR input image if it exists (the actual image used for OCR)
            # Otherwise use the preprocessed image from controller, or original
            image_path = None
            if hasattr(self.controller.state, 'ocr_input_image_path') and self.controller.state.ocr_input_image_path:
                if os.path.exists(self.controller.state.ocr_input_image_path):
                    image_path = self.controller.state.ocr_input_image_path
            if not image_path:
                image_path = self.controller.state.image_path if self.controller.state.image_path else self.image_path
            
            if image_path and os.path.exists(image_path):
                from PyQt6.QtWidgets import QScrollArea
                from PyQt6.QtCore import QPoint
                
                img = Image.open(image_path)
                
                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Create scroll area for large images with zoom support
                scroll_area = QScrollArea()
                scroll_area.setWidgetResizable(False)  # We'll control sizing for zoom
                scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # Create zoomable image widget
                zoomable_image = ZoomableImageWidget(img, scroll_area)
                scroll_area.setWidget(zoomable_image)
                
                # Store reference for potential updates
                self.ocr_image_widget = zoomable_image
                self.set_image_widget(scroll_area)
            else:
                self.set_image_widget(QLabel("No image loaded"))
            
            # Show OCR review widget in right pane
            self.set_text_widget(self.ocr_review_widget)
            
            # Display existing OCR results if available, but don't auto-run
            if self.controller.state.ocr_xml_path:
                self.display_ocr_results()
        
        elif stage == PipelineStage.LLM_CLEAN:
            # Show image in left pane (same as OCR stage)
            image_path = self.controller.state.image_path if self.controller.state.image_path else self.image_path
            if image_path and os.path.exists(image_path):
                from PyQt6.QtWidgets import QScrollArea
                img = Image.open(image_path)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                scroll_area = QScrollArea()
                scroll_area.setWidgetResizable(False)
                scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
                
                zoomable_image = ZoomableImageWidget(img, scroll_area)
                scroll_area.setWidget(zoomable_image)
                self.set_image_widget(scroll_area)
            else:
                self.set_image_widget(QLabel("No image loaded"))
            
            # Show LLM cleaning widget in right pane
            if not hasattr(self, 'llm_cleaning_widget'):
                from gui.stage_widgets import LLMCleaningWidget
                self.llm_cleaning_widget = LLMCleaningWidget(self.controller, self)
                self.llm_cleaning_widget.approve_signal.connect(self.on_llm_approve)
                self.llm_cleaning_widget.rerun_signal.connect(self.on_llm_rerun)
            else:
                # Reload text when navigating back to this stage
                self.llm_cleaning_widget.load_existing_text()
            
            self.set_text_widget(self.llm_cleaning_widget)
        
        elif stage == PipelineStage.MAPPING:
            # Show image in left pane (use OCR input image if available)
            image_path = None
            if hasattr(self.controller.state, 'ocr_input_image_path') and self.controller.state.ocr_input_image_path:
                if os.path.exists(self.controller.state.ocr_input_image_path):
                    image_path = self.controller.state.ocr_input_image_path
            if not image_path:
                image_path = self.controller.state.image_path if self.controller.state.image_path else self.image_path
            
            if image_path and os.path.exists(image_path):
                from PyQt6.QtWidgets import QScrollArea
                img = Image.open(image_path)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                scroll_area = QScrollArea()
                scroll_area.setWidgetResizable(False)
                scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
                
                zoomable_image = ZoomableImageWidget(img, scroll_area)
                scroll_area.setWidget(zoomable_image)
                self.set_image_widget(scroll_area)
            else:
                self.set_image_widget(QLabel("No image loaded"))
            
            # Show mapping review widget in right pane
            if not hasattr(self, 'mapping_review_widget'):
                from gui.stage_widgets import MappingReviewWidget
                self.mapping_review_widget = MappingReviewWidget(self.controller, self)
                self.mapping_review_widget.proceed_signal.connect(self.on_mapping_proceed)
            
            self.set_text_widget(self.mapping_review_widget)
            
            # Display mapping results if available
            if self.controller.state.hypothesis_list and self.controller.state.page:
                image_path_for_display = image_path or self.controller.state.image_path
                # Create LLM elements from clean text if available
                llm_elements = None
                if self.controller.state.clean_text:
                    from map_up_text import create_LLM_element_list
                    llm_elements = create_LLM_element_list(self.controller.state.clean_text)
                
                self.mapping_review_widget.display_mapping_results(
                    self.controller.state.hypothesis_list,
                    llm_elements=llm_elements,
                    image_path=image_path_for_display,
                    page=self.controller.state.page
                )
        
        self.status_bar.showMessage(f"Current stage: {stage.value}")
        
        # Update stage button states
        self.update_stage_button_states()
    
    def on_image_prep_proceed(self, config: dict):
        """Handle image prep proceed signal."""
        # Save the preprocessed image configuration
        if not self.image_path:
            QMessageBox.warning(self, "Warning", "No image loaded")
            return
        
        if not self.image_prep_widget.current_image:
            QMessageBox.warning(self, "Warning", "No image to process")
            return
        
        try:
            # Save the preprocessed image to a visible location in the output directory
            # Use a descriptive name so user can find it
            base_name = os.path.splitext(os.path.basename(self.image_path))[0]
            preprocessed_dir = os.path.join(self.controller.output_dir, base_name)
            os.makedirs(preprocessed_dir, exist_ok=True)
            preprocessed_path = os.path.join(preprocessed_dir, f"{base_name}_preprocessed_for_ocr.png")
            
            # Ensure RGB mode before saving
            img_to_save = self.image_prep_widget.current_image
            if img_to_save.mode != 'RGB':
                img_to_save = img_to_save.convert('RGB')
            img_to_save.save(preprocessed_path)
            
            # Update controller with preprocessed image and config
            self.controller.set_image(preprocessed_path, config)
            
            # Store the preprocessed path for later reference
            self.preprocessed_image_path = preprocessed_path
            
            # Move to OCR stage
            self.navigate_to_stage(PipelineStage.OCR)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save preprocessed image: {str(e)}")
    
    def run_ocr(self):
        """Run OCR on the current image."""
        if not self.controller.state.image_path:
            QMessageBox.warning(self, "Warning", "No image loaded")
            return
        
        try:
            self.status_bar.showMessage("Running OCR...")
            # Get language from OCR widget if available
            language = "eng"
            if hasattr(self.ocr_review_widget, 'language_combo'):
                language = self.ocr_review_widget.language_combo.currentText()
            
            # Run OCR
            self.controller.run_ocr(language=language)
            
            # Display results
            self.display_ocr_results()
            
            self.status_bar.showMessage("OCR complete")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"OCR failed: {str(e)}")
            self.status_bar.showMessage("OCR failed")
    
    def display_ocr_results(self):
        """Display OCR results in the OCR review widget."""
        if (self.controller.state.ocr_plaintext_path and 
            self.controller.state.ocr_xml_path and 
            self.controller.state.ocr_hocr_path):
            self.ocr_review_widget.display_ocr_results(
                self.controller.state.ocr_plaintext_path,
                self.controller.state.ocr_xml_path,
                self.controller.state.ocr_hocr_path
            )
    
    def on_ocr_approve(self):
        """Handle OCR approval."""
        # Enable next stage
        self.enable_stage(PipelineStage.LLM_CLEAN)
        # Navigate to LLM cleaning stage
        self.navigate_to_stage(PipelineStage.LLM_CLEAN)
        self.status_bar.showMessage("OCR approved - moved to LLM cleaning stage")
    
    def on_ocr_reject(self):
        """Handle OCR rejection."""
        # Allow user to re-run OCR or go back
        self.status_bar.showMessage("OCR rejected - you can re-run OCR")
    
    def on_llm_approve(self):
        """Handle LLM cleaning approval."""
        # Run mapping first
        try:
            self.status_bar.showMessage("Running mapping... This may take a moment.")
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()  # Update UI
            
            # Run mapping
            hypothesis_list, page = self.controller.run_mapping(show_ocr_accuracy=False)
            
            # Enable next stage
            self.enable_stage(PipelineStage.MAPPING)
            # Navigate to mapping stage (which will display the results)
            self.navigate_to_stage(PipelineStage.MAPPING)
            self.status_bar.showMessage("Mapping complete")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Mapping failed: {str(e)}")
            self.status_bar.showMessage("Mapping failed")
    
    def on_llm_rerun(self):
        """Handle LLM cleaning re-run request."""
        # Just update status, the widget will handle the re-run
        self.status_bar.showMessage("Re-running LLM cleaning...")
    
    def on_mapping_proceed(self):
        """Handle mapping proceed signal."""
        # Enable next stage
        self.enable_stage(PipelineStage.PDF_GEN)
        # Navigate to PDF generation stage
        self.navigate_to_stage(PipelineStage.PDF_GEN)
        self.status_bar.showMessage("Mapping approved - moved to PDF generation stage")
    
    def navigate_to_stage(self, stage: PipelineStage):
        """Navigate to a specific pipeline stage."""
        self.current_stage = stage
        self.stage_changed.emit(stage)
    
    def save_current(self):
        """Save current work."""
        # This will be implemented by stage widgets
        QMessageBox.information(self, "Save", "Save functionality will be implemented by stage widgets")
    
    def set_image_widget(self, widget: QWidget):
        """Set the widget for the image pane."""
        # Clear existing widgets (but don't delete persistent widgets)
        while self.image_layout.count():
            child = self.image_layout.takeAt(0)
            if child.widget():
                # Only delete if it's not a persistent widget we want to keep
                widget_to_delete = child.widget()
                # Don't delete if it's one of our persistent widgets
                if widget_to_delete != self.image_prep_widget:
                    widget_to_delete.deleteLater()
        
        self.image_layout.addWidget(widget)
    
    def set_text_widget(self, widget: QWidget):
        """Set the widget for the text pane."""
        # Clear existing widgets
        while self.text_layout.count():
            child = self.text_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        self.text_layout.addWidget(widget)
    
    def enable_stage(self, stage: PipelineStage):
        """Enable a stage button."""
        if stage in self.stage_buttons:
            self.stage_buttons[stage].setEnabled(True)
    
    def update_stage_button_states(self):
        """Update stage button enabled states based on current stage and progress."""
        # Check if stage_buttons exists and is initialized
        if not hasattr(self, 'stage_buttons') or not self.stage_buttons:
            return
        
        # Enable Image Prep always (can go back to it)
        if PipelineStage.IMAGE_PREP in self.stage_buttons and self.stage_buttons[PipelineStage.IMAGE_PREP] is not None:
            self.stage_buttons[PipelineStage.IMAGE_PREP].setEnabled(True)
        
        # Enable OCR if we have an image
        if PipelineStage.OCR in self.stage_buttons and self.stage_buttons[PipelineStage.OCR] is not None:
            has_image = bool(self.image_path is not None or 
                            (hasattr(self.controller, 'state') and 
                             hasattr(self.controller.state, 'image_path') and
                             self.controller.state.image_path is not None))
            self.stage_buttons[PipelineStage.OCR].setEnabled(has_image)
        
        # Enable subsequent stages only if previous stages are complete
        if PipelineStage.LLM_CLEAN in self.stage_buttons and self.stage_buttons[PipelineStage.LLM_CLEAN] is not None:
            has_ocr = bool(hasattr(self.controller, 'state') and 
                          hasattr(self.controller.state, 'ocr_xml_path') and
                          self.controller.state.ocr_xml_path is not None)
            self.stage_buttons[PipelineStage.LLM_CLEAN].setEnabled(has_ocr)
        
        if PipelineStage.MAPPING in self.stage_buttons and self.stage_buttons[PipelineStage.MAPPING] is not None:
            has_clean = bool(hasattr(self.controller, 'state') and 
                            hasattr(self.controller.state, 'clean_text_path') and
                            self.controller.state.clean_text_path is not None)
            self.stage_buttons[PipelineStage.MAPPING].setEnabled(has_clean)
        
        if PipelineStage.PDF_GEN in self.stage_buttons and self.stage_buttons[PipelineStage.PDF_GEN] is not None:
            has_mapping = bool(hasattr(self.controller, 'state') and 
                              hasattr(self.controller.state, 'hypothesis_list') and
                              self.controller.state.hypothesis_list is not None)
            self.stage_buttons[PipelineStage.PDF_GEN].setEnabled(has_mapping)
    
    def update_status(self, message: str):
        """Update status bar message."""
        self.status_bar.showMessage(message)
    
    def showEvent(self, event):
        """Handle window show event - ensure open action is enabled."""
        super().showEvent(event)
        if self.open_action:
            self.open_action.setEnabled(True)


class ZoomableImageWidget(QLabel):
    """Widget for displaying and zooming images with scroll wheel."""
    
    def __init__(self, image: Image.Image, scroll_area: QWidget, parent=None):
        super().__init__(parent)
        self.original_image = image
        self.scroll_area = scroll_area
        self.zoom_factor = 1.0  # Start at fit-to-height
        self.show_gridlines = False  # Whether to show gridlines
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(400, 300)
        
        # Calculate initial size to fit height
        self.update_display()
    
    def update_display(self):
        """Update image display based on current zoom factor."""
        if self.original_image is None:
            return
        
        # Get available height from scroll area viewport
        if self.scroll_area:
            available_height = self.scroll_area.viewport().height() - 20
            available_width = self.scroll_area.viewport().width() - 20
            
            if available_height > 0:
                # Calculate fit-to-height ratio
                img_width, img_height = self.original_image.size
                height_ratio = available_height / img_height
                width_ratio = available_width / img_width if available_width > 0 else height_ratio
                fit_ratio = min(height_ratio, width_ratio, 1.0)  # Don't upscale beyond original
                
                # Apply zoom factor
                display_ratio = fit_ratio * self.zoom_factor
                
                # Calculate display size
                display_width = int(img_width * display_ratio)
                display_height = int(img_height * display_ratio)
                
                # Resize image
                display_img = self.original_image.resize((display_width, display_height), Image.Resampling.LANCZOS)
                
                # Draw gridlines if enabled
                if self.show_gridlines:
                    from PIL import ImageDraw
                    draw = ImageDraw.Draw(display_img)
                    img_width, img_height = display_img.size
                    
                    # Draw gridlines (every 50 pixels, with thicker lines every 200 pixels)
                    grid_spacing = 50
                    major_grid_spacing = 200
                    
                    # Vertical lines
                    for x in range(0, img_width + 1, grid_spacing):
                        if x % major_grid_spacing == 0:
                            # Major gridline (thicker)
                            draw.line([(x, 0), (x, img_height)], fill=(128, 128, 128), width=2)
                        else:
                            # Minor gridline (thinner)
                            draw.line([(x, 0), (x, img_height)], fill=(200, 200, 200), width=1)
                    
                    # Horizontal lines
                    for y in range(0, img_height + 1, grid_spacing):
                        if y % major_grid_spacing == 0:
                            # Major gridline (thicker)
                            draw.line([(0, y), (img_width, y)], fill=(128, 128, 128), width=2)
                        else:
                            # Minor gridline (thinner)
                            draw.line([(0, y), (img_width, y)], fill=(200, 200, 200), width=1)
                
                # Convert to pixmap
                if display_img.mode != 'RGB':
                    display_img = display_img.convert('RGB')
                pixmap = QPixmap.fromImage(ImageQt(display_img))
                self.setPixmap(pixmap)
                self.resize(pixmap.size())
    
    def wheelEvent(self, event: QWheelEvent):
        """Handle scroll wheel events for zooming."""
        # Check for Cmd key (Mac) or Ctrl key (Windows/Linux)
        modifiers = event.modifiers()
        if modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
            # Zoom in/out
            delta = event.angleDelta().y()
            if delta > 0:
                # Zoom in
                self.zoom_factor = min(self.zoom_factor * 1.1, 5.0)  # Max 5x zoom
            else:
                # Zoom out
                self.zoom_factor = max(self.zoom_factor / 1.1, 0.1)  # Min 0.1x zoom
            
            self.update_display()
            event.accept()
        else:
            # Normal scrolling
            super().wheelEvent(event)
    
    def resizeEvent(self, event):
        """Handle resize events to maintain fit-to-height."""
        super().resizeEvent(event)
        # Recalculate display if viewport size changed
        if self.zoom_factor == 1.0:  # Only auto-fit if at default zoom
            self.update_display()

