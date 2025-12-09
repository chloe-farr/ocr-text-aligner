"""
Stage-specific widgets for the OCR pipeline GUI.

Contains widgets for each pipeline stage: image prep, OCR review,
LLM cleaning, mapping review, and PDF generation.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
    QTextEdit, QComboBox, QLineEdit, QGroupBox, QSpinBox, QDoubleSpinBox,
    QFileDialog, QMessageBox, QScrollArea, QCheckBox, QProgressBar
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QPixmap, QImage
from PIL import Image
from PIL.ImageQt import ImageQt
import os

from pipeline_controller import PipelineController, PipelineStage
import tesseract_ocr
import llm_cleaning
from gui.error_highlighter import ErrorHighlighter, update_word_correction
from map_up_text import TokenHypotheses, TokenCandidate, LLMToken, create_LLM_element_list
import text_utils
import xml_obj as XMLOBJ


class ImagePrepWidget(QWidget):
    """Widget for image preparation stage - image display only."""
    
    def __init__(self, controller: PipelineController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.original_image = None
        self.current_image = None
        self.crop_bbox = None  # (left, top, right, bottom) in original image coordinates
        self.crop_start = None
        self.crop_end = None
        self.is_cropping = False
        self.display_scale = 1.0  # Scale factor between displayed image and original
        self.display_offset_x = 0
        self.display_offset_y = 0
        self.init_ui()
    
    def init_ui(self):
        """Initialize UI components - image display only."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Image display area with mouse interaction for cropping
        self.image_label = QLabel("No image loaded")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(400, 300)
        self.image_label.setStyleSheet("border: 1px solid gray;")
        self.image_label.mousePressEvent = self.on_image_mouse_press
        self.image_label.mouseMoveEvent = self.on_image_mouse_move
        self.image_label.mouseReleaseEvent = self.on_image_mouse_release
        self.image_label.setMouseTracking(True)
        layout.addWidget(self.image_label)


class ImagePrepControlsWidget(QWidget):
    """Widget for image preparation controls - right pane."""
    
    proceed_signal = pyqtSignal(dict)  # Emits prep config
    
    def __init__(self, image_prep_widget: ImagePrepWidget, controller: PipelineController, parent=None):
        super().__init__(parent)
        self.image_prep_widget = image_prep_widget  # Reference to the image display widget
        self.controller = controller
        self.init_ui()
    
    def init_ui(self):
        """Initialize UI components - controls only."""
        layout = QVBoxLayout(self)
        
        # Controls
        controls_group = QGroupBox("Image Controls")
        controls_layout = QVBoxLayout()
        
        # Crop section
        crop_group = QGroupBox("Crop")
        crop_layout = QVBoxLayout()
        
        crop_buttons_layout = QHBoxLayout()
        self.crop_btn = QPushButton("Start Crop")
        self.crop_btn.clicked.connect(lambda: self.image_prep_widget.toggle_crop_mode_internal())
        crop_buttons_layout.addWidget(self.crop_btn)
        
        self.apply_crop_btn = QPushButton("Apply Crop")
        self.apply_crop_btn.clicked.connect(lambda: self.image_prep_widget.apply_crop_internal())
        self.apply_crop_btn.setEnabled(False)
        crop_buttons_layout.addWidget(self.apply_crop_btn)
        
        self.clear_crop_btn = QPushButton("Clear Crop")
        self.clear_crop_btn.clicked.connect(lambda: self.image_prep_widget.clear_crop_internal())
        self.clear_crop_btn.setEnabled(False)
        crop_buttons_layout.addWidget(self.clear_crop_btn)
        
        crop_layout.addLayout(crop_buttons_layout)
        crop_group.setLayout(crop_layout)
        controls_layout.addWidget(crop_group)
        
        # Rotation
        rotation_group = QGroupBox("Rotation")
        rotation_layout = QVBoxLayout()
        
        rotation_controls = QHBoxLayout()
        rotation_controls.addWidget(QLabel("Angle:"))
        self.rotation_spinbox = QDoubleSpinBox()
        self.rotation_spinbox.setRange(-180.0, 180.0)
        self.rotation_spinbox.setSingleStep(0.01)  # 0.01 degree increments
        self.rotation_spinbox.setDecimals(2)  # Show 2 decimal places
        self.rotation_spinbox.setValue(0.0)
        self.rotation_spinbox.setSuffix("°")
        self.rotation_spinbox.valueChanged.connect(lambda v: self.update_rotation(v))
        rotation_controls.addWidget(self.rotation_spinbox)
        
        # Quick rotation buttons
        quick_rot_layout = QHBoxLayout()
        rot_minus_5 = QPushButton("-5°")
        rot_minus_5.clicked.connect(lambda: self.rotation_spinbox.setValue(self.rotation_spinbox.value() - 5.0))
        quick_rot_layout.addWidget(rot_minus_5)
        
        rot_plus_5 = QPushButton("+5°")
        rot_plus_5.clicked.connect(lambda: self.rotation_spinbox.setValue(self.rotation_spinbox.value() + 5.0))
        quick_rot_layout.addWidget(rot_plus_5)
        
        rotation_layout.addLayout(rotation_controls)
        rotation_layout.addLayout(quick_rot_layout)
        rotation_group.setLayout(rotation_layout)
        controls_layout.addWidget(rotation_group)
        
        # Contrast
        contrast_group = QGroupBox("Contrast")
        contrast_layout = QHBoxLayout()
        contrast_layout.addWidget(QLabel("Factor:"))
        self.contrast_slider = QSlider(Qt.Orientation.Horizontal)
        self.contrast_slider.setRange(0, 200)
        self.contrast_slider.setValue(100)
        self.contrast_slider.valueChanged.connect(lambda v: self.update_contrast(v))
        contrast_layout.addWidget(self.contrast_slider)
        self.contrast_label = QLabel("1.0")
        self.contrast_label.setMinimumWidth(50)
        contrast_layout.addWidget(self.contrast_label)
        contrast_group.setLayout(contrast_layout)
        controls_layout.addWidget(contrast_group)
        
        # Brightness
        brightness_group = QGroupBox("Brightness")
        brightness_layout = QHBoxLayout()
        brightness_layout.addWidget(QLabel("Factor:"))
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(0, 200)
        self.brightness_slider.setValue(100)
        self.brightness_slider.valueChanged.connect(lambda v: self.update_brightness(v))
        brightness_layout.addWidget(self.brightness_slider)
        self.brightness_label = QLabel("1.0")
        self.brightness_label.setMinimumWidth(50)
        brightness_layout.addWidget(self.brightness_label)
        brightness_group.setLayout(brightness_layout)
        controls_layout.addWidget(brightness_group)
        
        # Zoom controls
        zoom_group = QGroupBox("Zoom")
        zoom_layout = QVBoxLayout()
        
        zoom_buttons_layout = QHBoxLayout()
        zoom_out_btn = QPushButton("Zoom Out")
        zoom_out_btn.clicked.connect(self.zoom_out)
        zoom_buttons_layout.addWidget(zoom_out_btn)
        
        fit_btn = QPushButton("Fit to Height")
        fit_btn.clicked.connect(self.fit_to_height)
        zoom_buttons_layout.addWidget(fit_btn)
        
        zoom_in_btn = QPushButton("Zoom In")
        zoom_in_btn.clicked.connect(self.zoom_in)
        zoom_buttons_layout.addWidget(zoom_in_btn)
        
        zoom_layout.addLayout(zoom_buttons_layout)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zoom_layout.addWidget(self.zoom_label)
        zoom_group.setLayout(zoom_layout)
        controls_layout.addWidget(zoom_group)
        
        # Display options
        display_group = QGroupBox("Display Options")
        display_layout = QVBoxLayout()
        
        self.show_grid_checkbox = QCheckBox("Show Gridlines")
        self.show_grid_checkbox.setChecked(False)
        self.show_grid_checkbox.stateChanged.connect(self.toggle_gridlines)
        display_layout.addWidget(self.show_grid_checkbox)
        
        display_group.setLayout(display_layout)
        controls_layout.addWidget(display_group)
        
        # Action buttons
        action_layout = QHBoxLayout()
        reset_btn = QPushButton("Reset All")
        reset_btn.clicked.connect(lambda: self.reset_image())
        action_layout.addWidget(reset_btn)
        
        controls_layout.addLayout(action_layout)
        controls_group.setLayout(controls_layout)
        layout.addWidget(controls_group)
        
        # Proceed button
        proceed_btn = QPushButton("Proceed to OCR")
        proceed_btn.clicked.connect(self.proceed)
        layout.addWidget(proceed_btn)
    
    def get_rotation_value(self):
        """Get current rotation value."""
        return self.rotation_spinbox.value()
    
    def get_contrast_value(self):
        """Get current contrast value."""
        return self.contrast_slider.value() / 100.0
    
    def get_brightness_value(self):
        """Get current brightness value."""
        return self.brightness_slider.value() / 100.0
    
    def update_rotation(self, value):
        """Update rotation and trigger image display update."""
        # No need to update label since spinbox has suffix
        if self.image_prep_widget:
            self.image_prep_widget.apply_transforms()
    
    def update_contrast(self, value):
        """Update contrast label and trigger image display update."""
        contrast_factor = value / 100.0
        self.contrast_label.setText(f"{contrast_factor:.2f}")
        if self.image_prep_widget:
            self.image_prep_widget.apply_transforms()
    
    def update_brightness(self, value):
        """Update brightness label and trigger image display update."""
        brightness_factor = value / 100.0
        self.brightness_label.setText(f"{brightness_factor:.2f}")
        if self.image_prep_widget:
            self.image_prep_widget.apply_transforms()
    
    def reset_image(self):
        """Reset all image transformations to defaults."""
        self.rotation_spinbox.setValue(0.0)
        self.contrast_slider.setValue(100)
        self.brightness_slider.setValue(100)
        # Update labels
        self.contrast_label.setText("1.0")
        self.brightness_label.setText("1.0")
        # Reset zoom
        if self.image_prep_widget:
            self.image_prep_widget.zoom_factor = 1.0
            self.zoom_label.setText("100%")
        # Reset image in display widget
        if self.image_prep_widget and self.image_prep_widget.original_image:
            self.image_prep_widget.current_image = self.image_prep_widget.original_image.copy()
            self.image_prep_widget.update_display()
    
    def zoom_in(self):
        """Zoom in on the image."""
        if self.image_prep_widget:
            self.image_prep_widget.zoom_factor = min(self.image_prep_widget.zoom_factor * 1.25, 5.0)  # Max 5x zoom
            self.zoom_label.setText(f"{int(self.image_prep_widget.zoom_factor * 100)}%")
            self.image_prep_widget.update_display()
    
    def zoom_out(self):
        """Zoom out on the image."""
        if self.image_prep_widget:
            self.image_prep_widget.zoom_factor = max(self.image_prep_widget.zoom_factor / 1.25, 0.1)  # Min 0.1x zoom
            self.zoom_label.setText(f"{int(self.image_prep_widget.zoom_factor * 100)}%")
            self.image_prep_widget.update_display()
    
    def fit_to_height(self):
        """Reset zoom to fit image to height."""
        if self.image_prep_widget:
            self.image_prep_widget.zoom_factor = 1.0
            self.zoom_label.setText("100%")
            self.image_prep_widget.update_display()
    
    def toggle_gridlines(self, state):
        """Toggle gridlines display."""
        if self.image_prep_widget:
            self.image_prep_widget.show_gridlines = (state == Qt.CheckState.Checked.value)
            self.image_prep_widget.update_display()
    
    def proceed(self):
        """Emit proceed signal with current config."""
        config = {
            'rotate': self.get_rotation_value(),
            'contrast': self.get_contrast_value(),
            'brightness': self.get_brightness_value()
        }
        self.proceed_signal.emit(config)


class ImagePrepWidget(QWidget):
    """Widget for image preparation stage - image display only."""
    
    def __init__(self, controller: PipelineController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.original_image = None
        self.current_image = None
        self.crop_bbox = None  # (left, top, right, bottom) in original image coordinates
        self.crop_start = None
        self.crop_end = None
        self.crop_preview = None  # Preview point while moving mouse (before second click)
        self.is_cropping = False
        self.display_scale = 1.0  # Scale factor between displayed image and original
        self.zoom_factor = 1.0  # User-controlled zoom level (1.0 = fit to height)
        self.current_image_size = None  # Size of current_image (for coordinate conversion)
        self.display_offset_x = 0
        self.display_offset_y = 0
        self.scroll_area = None  # Reference to scroll area
        self.controls_widget = None  # Reference to controls widget
        self.show_gridlines = False  # Whether to show gridlines
        self.init_ui()
    
    def set_controls_widget(self, controls_widget):
        """Set reference to controls widget."""
        self.controls_widget = controls_widget
    
    def init_ui(self):
        """Initialize UI components - image display only."""
        from PyQt6.QtWidgets import QScrollArea
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create scroll area for large images with zoom support
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)  # We'll control sizing for zoom
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Image display area with mouse interaction for cropping
        self.image_label = QLabel("No image loaded")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(400, 300)
        self.image_label.setStyleSheet("border: 1px solid gray;")
        self.image_label.mousePressEvent = self.on_image_mouse_press
        self.image_label.mouseMoveEvent = self.on_image_mouse_move
        self.image_label.mouseReleaseEvent = self.on_image_mouse_release
        self.image_label.setMouseTracking(True)
        
        self.scroll_area.setWidget(self.image_label)
        layout.addWidget(self.scroll_area)
    
    def load_image(self, image_path: str):
        """Load image for editing."""
        try:
            self.original_image = Image.open(image_path)
            self.current_image = self.original_image.copy()
            self.crop_bbox = None
            self.crop_start = None
            self.crop_end = None
            self.is_cropping = False
            self.update_display()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load image: {str(e)}")
    
    def update_display(self):
        """Update image display with crop overlay if active."""
        if self.current_image is None:
            return
        
        # Create a deep copy to ensure we never modify the original
        display_img = self.current_image.copy()
        current_size = display_img.size  # Size of current_image (may have transforms)
        
        # Convert to RGB if necessary (ImageQt requires RGB mode)
        if display_img.mode != 'RGB':
            display_img = display_img.convert('RGB')
        
        # Store the current image size for coordinate conversion
        self.current_image_size = current_size
        
        # Calculate display size based on fit-to-height and zoom
        if self.scroll_area:
            # Get available height from scroll area
            available_height = self.scroll_area.viewport().height() - 20  # Leave some margin
            available_width = self.scroll_area.viewport().width() - 20
            
            # Calculate size to fit height initially (if zoom is 1.0)
            if available_height > 0:
                # Fit to height
                height_ratio = available_height / current_size[1]
                # Also check width constraint
                width_ratio = available_width / current_size[0] if available_width > 0 else height_ratio
                # Use the smaller ratio to fit within both constraints
                fit_ratio = min(height_ratio, width_ratio, 1.0)  # Don't upscale beyond original
                
                # Apply zoom factor
                display_ratio = fit_ratio * self.zoom_factor
                
                # Calculate display size
                display_width = int(current_size[0] * display_ratio)
                display_height = int(current_size[1] * display_ratio)
                
                # Resize image for display
                if display_width != current_size[0] or display_height != current_size[1]:
                    display_img = display_img.resize((display_width, display_height), Image.Resampling.LANCZOS)
                
                # Calculate scale factor for coordinate conversion
                self.display_scale = display_ratio
            else:
                # Fallback if scroll area not ready
                self.display_scale = 1.0
        else:
            # Fallback if no scroll area
            self.display_scale = 1.0
        
        # Calculate offset to center image in label (for crop rectangle drawing)
        pixmap_size = display_img.size  # This is a tuple (width, height)
        self.display_offset_x = 0  # No offset needed with scroll area
        self.display_offset_y = 0
        
        # Draw gridlines if enabled
        if self.show_gridlines:
            from PIL import ImageDraw
            draw = ImageDraw.Draw(display_img)
            img_width, img_height = display_img.size
            
            # Draw gridlines (every 50 pixels, with thicker lines every 200 pixels)
            grid_spacing = 25
            major_grid_spacing = 100
            
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
        
        # Draw crop rectangle if cropping (draw on the display copy only)
        if self.is_cropping and self.crop_start:
            from PIL import ImageDraw
            # Create a fresh drawing context on the display image (may already exist from gridlines)
            if not self.show_gridlines:
                draw = ImageDraw.Draw(display_img)
            else:
                # Reuse existing draw context
                draw = ImageDraw.Draw(display_img)
            
            # Use preview point if end point not set yet
            end_point = self.crop_end if self.crop_end else self.crop_preview
            if end_point:
                # Crop coordinates are in display image coordinates (thumbnail space)
                # They were calculated relative to the pixmap, so use them directly
                x1 = min(self.crop_start.x(), end_point.x())
                y1 = min(self.crop_start.y(), end_point.y())
                x2 = max(self.crop_start.x(), end_point.x())
                y2 = max(self.crop_start.y(), end_point.y())
                
                # Clamp to display image bounds
                img_width, img_height = display_img.size
                x1 = max(0, min(int(x1), img_width))
                y1 = max(0, min(int(y1), img_height))
                x2 = max(0, min(int(x2), img_width))
                y2 = max(0, min(int(y2), img_height))
                
                # Draw rectangle
                if x2 > x1 and y2 > y1:
                    draw.rectangle([x1, y1, x2, y2], outline=(255, 0, 0), width=2)
        
        # Convert to QPixmap for display
        try:
            qimage = ImageQt(display_img)
            pixmap = QPixmap.fromImage(qimage)
            self.image_label.setPixmap(pixmap)
            # Set label size to match pixmap size for proper scrolling
            self.image_label.resize(pixmap.size())
            # Update zoom label if controls widget exists
            if self.controls_widget and hasattr(self.controls_widget, 'zoom_label'):
                self.controls_widget.zoom_label.setText(f"{int(self.zoom_factor * 100)}%")
        except Exception as e:
            # If conversion fails, try converting to RGB first
            if display_img.mode != 'RGB':
                display_img = display_img.convert('RGB')
                qimage = ImageQt(display_img)
                pixmap = QPixmap.fromImage(qimage)
                self.image_label.setPixmap(pixmap)
                self.image_label.resize(pixmap.size())
            else:
                # If still fails, show error
                self.image_label.setText(f"Display error: {str(e)}")
    
    def toggle_crop_mode(self):
        """Toggle crop mode on/off."""
        if self.controls_widget:
            self.controls_widget.toggle_crop_mode()
    
    def toggle_crop_mode_internal(self):
        """Internal method to toggle crop mode."""
        self.is_cropping = not self.is_cropping
        if self.controls_widget:
            if self.is_cropping:
                self.controls_widget.crop_btn.setText("Cancel Crop")
            else:
                self.controls_widget.crop_btn.setText("Start Crop")
        self.crop_start = None
        self.crop_end = None
        self.crop_preview = None  # Preview point while moving mouse
        self.update_display()
    
    def on_image_mouse_press(self, event):
        """Handle mouse press for crop selection - click to set points."""
        if not self.is_cropping or self.current_image is None:
            return
        
        # Convert click position to image coordinates
        click_x = event.position().x() - self.display_offset_x
        click_y = event.position().y() - self.display_offset_y
        
        # Check if click is within image bounds
        pixmap = self.image_label.pixmap()
        if pixmap is None:
            return
        
        if 0 <= click_x < pixmap.width() and 0 <= click_y < pixmap.height():
            from PyQt6.QtCore import QPoint
            click_point = QPoint(int(click_x), int(click_y))
            
            if self.crop_start is None:
                # First click - set start point
                self.crop_start = click_point
                self.crop_end = None
                self.crop_preview = click_point
            else:
                # Second click - set end point
                self.crop_end = click_point
                self.crop_preview = None
                # Enable apply button if selection is valid
                width = abs(self.crop_end.x() - self.crop_start.x())
                height = abs(self.crop_end.y() - self.crop_start.y())
                if width > 10 and height > 10:  # Minimum crop size
                    if self.controls_widget:
                        self.controls_widget.apply_crop_btn.setEnabled(True)
            
            self.update_display()
    
    def on_image_mouse_move(self, event):
        """Handle mouse move for crop selection preview."""
        if not self.is_cropping or self.crop_start is None or self.crop_end is not None:
            # Only show preview if we have start point but not end point
            return
        
        # Get mouse position relative to the label
        click_x = event.position().x()
        click_y = event.position().y()
        
        pixmap = self.image_label.pixmap()
        if pixmap is None:
            return
        
        # Clamp to image bounds
        click_x = max(0, min(click_x, pixmap.width()))
        click_y = max(0, min(click_y, pixmap.height()))
        
        from PyQt6.QtCore import QPoint
        new_preview = QPoint(int(click_x), int(click_y))
        
        # Only update if preview point actually changed significantly (to avoid constant redraws)
        # Update if it's the first preview or if moved more than 5 pixels
        if self.crop_preview is None:
            self.crop_preview = new_preview
            self.update_display()
        else:
            # Only update if moved significantly
            dx = abs(new_preview.x() - self.crop_preview.x())
            dy = abs(new_preview.y() - self.crop_preview.y())
            if dx > 5 or dy > 5:  # Throttle updates to every 5 pixels
                self.crop_preview = new_preview
                self.update_display()
    
    def on_image_mouse_release(self, event):
        """Handle mouse release - not used in click-to-set mode."""
        # In click-to-set mode, we don't need mouse release
        pass
    
    def apply_crop(self):
        """Apply the crop selection to the image."""
        if not self.crop_start or not self.crop_end or self.original_image is None:
            return
        
        # Convert display coordinates to original image coordinates
        # First, convert to display image coordinates
        x1 = min(self.crop_start.x(), self.crop_end.x())
        y1 = min(self.crop_start.y(), self.crop_end.y())
        x2 = max(self.crop_start.x(), self.crop_end.x())
        y2 = max(self.crop_start.y(), self.crop_end.y())
        
        # Scale back to original image size
        x1 = int(x1 / self.display_scale)
        y1 = int(y1 / self.display_scale)
        x2 = int(x2 / self.display_scale)
        y2 = int(y2 / self.display_scale)
        
        # Clamp to image bounds
        orig_width, orig_height = self.original_image.size
        x1 = max(0, min(x1, orig_width))
        y1 = max(0, min(y1, orig_height))
        x2 = max(0, min(x2, orig_width))
        y2 = max(0, min(y2, orig_height))
        
        # Ensure valid bbox
        if x2 > x1 and y2 > y1:
            self.crop_bbox = (x1, y1, x2, y2)
            from image_preprocessing import crop_image
            self.original_image = crop_image(self.original_image, self.crop_bbox)
            self.current_image = self.original_image.copy()
            self.crop_bbox = None  # Reset after applying
            self.is_cropping = False
            self.crop_btn.setText("Start Crop")
            self.apply_crop_btn.setEnabled(False)
            self.clear_crop_btn.setEnabled(False)
            self.crop_start = None
            self.crop_end = None
            # Reapply other transforms
            self.apply_transforms()
    
    def clear_crop(self):
        """Clear the crop selection without applying."""
        self.crop_start = None
        self.crop_end = None
        self.apply_crop_btn.setEnabled(False)
        self.update_display()
    
    def apply_transforms(self):
        """Apply all transformations to image."""
        if self.original_image is None or not self.controls_widget:
            return
        
        from image_preprocessing import rotate_image, adjust_contrast, adjust_brightness
        
        # Always start with a fresh copy of the original
        img = self.original_image.copy()
        
        # Ensure RGB mode for all operations
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Apply rotation
        rotation = self.controls_widget.get_rotation_value()
        if rotation != 0:
            img = rotate_image(img, rotation)
            # Ensure still RGB after rotation (some rotations might change mode)
            if img.mode != 'RGB':
                img = img.convert('RGB')
        
        # Apply contrast
        contrast = self.controls_widget.get_contrast_value()
        if contrast != 1.0:
            img = adjust_contrast(img, contrast)
        
        # Apply brightness
        brightness = self.controls_widget.get_brightness_value()
        if brightness != 1.0:
            img = adjust_brightness(img, brightness)
        
        # Store the transformed image
        self.current_image = img
        self.update_display()
    
    def apply_crop_internal(self):
        """Internal method to apply crop."""
        if not self.crop_start or not self.crop_end or self.current_image is None:
            return
        
        # Convert display coordinates (thumbnail space) to current_image coordinates
        # Crop coordinates are in the displayed thumbnail space
        x1 = min(self.crop_start.x(), self.crop_end.x())
        y1 = min(self.crop_start.y(), self.crop_end.y())
        x2 = max(self.crop_start.x(), self.crop_end.x())
        y2 = max(self.crop_start.y(), self.crop_end.y())
        
        # Scale back to current_image size (the image that's actually displayed, with transforms)
        x1 = int(x1 / self.display_scale)
        y1 = int(y1 / self.display_scale)
        x2 = int(x2 / self.display_scale)
        y2 = int(y2 / self.display_scale)
        
        # Clamp to current_image bounds
        if not hasattr(self, 'current_image_size'):
            self.current_image_size = self.current_image.size
        curr_width, curr_height = self.current_image_size
        x1 = max(0, min(x1, curr_width))
        y1 = max(0, min(y1, curr_height))
        x2 = max(0, min(x2, curr_width))
        y2 = max(0, min(y2, curr_height))
        
        # Ensure valid bbox
        if x2 > x1 and y2 > y1:
            self.crop_bbox = (x1, y1, x2, y2)
            from image_preprocessing import crop_image
            # Crop the current_image (which may have transforms applied)
            self.current_image = crop_image(self.current_image, self.crop_bbox)
            # Also update original_image to match (crop is applied to the transformed image)
            # If we want to preserve the ability to reset, we'd need to track the crop separately
            # For now, update original_image to the cropped current_image
            self.original_image = self.current_image.copy()
            self.crop_bbox = None  # Reset after applying
            self.is_cropping = False
            if self.controls_widget:
                self.controls_widget.crop_btn.setText("Start Crop")
                self.controls_widget.apply_crop_btn.setEnabled(False)
                self.controls_widget.clear_crop_btn.setEnabled(False)
            self.crop_start = None
            self.crop_end = None
            self.crop_preview = None
            # Update display (no need to reapply transforms since we cropped the already-transformed image)
            self.update_display()
    
    def clear_crop_internal(self):
        """Internal method to clear crop."""
        self.crop_start = None
        self.crop_end = None
        self.crop_preview = None
        if self.controls_widget:
            self.controls_widget.apply_crop_btn.setEnabled(False)
        self.update_display()


class OCRReviewWidget(QWidget):
    """Widget for reviewing OCR output."""
    
    approve_signal = pyqtSignal()
    reject_signal = pyqtSignal()
    
    def __init__(self, controller: PipelineController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.init_ui()
    
    def init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        
        # OCR settings
        settings_group = QGroupBox("OCR Settings")
        settings_layout = QVBoxLayout()
        
        # Language selection
        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel("Language:"))
        self.language_combo = QComboBox()
        try:
            langs = tesseract_ocr.get_available_languages()
            self.language_combo.addItems(langs)
            if 'eng' in langs:
                self.language_combo.setCurrentText('eng')
        except:
            self.language_combo.addItem('eng')
        lang_layout.addWidget(self.language_combo)
        settings_layout.addLayout(lang_layout)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        # Display options
        display_group = QGroupBox("Display Options")
        display_layout = QVBoxLayout()
        
        self.show_grid_checkbox = QCheckBox("Show Gridlines")
        self.show_grid_checkbox.setChecked(False)
        self.show_grid_checkbox.stateChanged.connect(self.toggle_gridlines)
        display_layout.addWidget(self.show_grid_checkbox)
        
        display_group.setLayout(display_layout)
        layout.addWidget(display_group)
        
        # Run OCR button
        self.run_ocr_btn = QPushButton("Run OCR")
        self.run_ocr_btn.clicked.connect(self.run_ocr)
        layout.addWidget(self.run_ocr_btn)
        
        # OCR Status indicator (initially hidden)
        status_layout = QVBoxLayout()
        self.ocr_status_label = QLabel("")
        self.ocr_status_label.setStyleSheet("""
            QLabel {
                background-color: #e3f2fd;
                border: 2px solid #2196f3;
                border-radius: 5px;
                padding: 10px;
                font-weight: bold;
                color: #1976d2;
            }
        """)
        self.ocr_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ocr_status_label.hide()
        
        # Progress bar (indeterminate/busy style)
        self.ocr_progress = QProgressBar()
        self.ocr_progress.setRange(0, 0)  # Indeterminate mode
        self.ocr_progress.setStyleSheet("""
            QProgressBar {
                border: 2px solid #2196f3;
                border-radius: 5px;
                text-align: center;
                background-color: #e3f2fd;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #2196f3;
                border-radius: 3px;
            }
        """)
        self.ocr_progress.hide()
        
        status_layout.addWidget(self.ocr_status_label)
        status_layout.addWidget(self.ocr_progress)
        layout.addLayout(status_layout)
        
        # Text display (read-only, non-selectable)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)  # Display only
        self.text_edit.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)  # Disable text selection
        layout.addWidget(QLabel("OCR Plaintext (display only):"))
        layout.addWidget(self.text_edit)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        open_xml_btn = QPushButton("Show XML Location")
        open_xml_btn.clicked.connect(self.open_xml)
        btn_layout.addWidget(open_xml_btn)
        
        open_hocr_btn = QPushButton("Show hOCR Location")
        open_hocr_btn.clicked.connect(self.open_hocr)
        btn_layout.addWidget(open_hocr_btn)
        
        generate_pdf_btn = QPushButton("Generate Tesseract PDF")
        generate_pdf_btn.clicked.connect(self.generate_tesseract_pdf)
        btn_layout.addWidget(generate_pdf_btn)
        
        layout.addLayout(btn_layout)
        
        # Show OCR input image button
        show_input_btn = QPushButton("Show Image Used for OCR")
        show_input_btn.clicked.connect(self.show_ocr_input_image)
        layout.addWidget(show_input_btn)
        
        # Approval buttons
        approval_layout = QHBoxLayout()
        
        approve_btn = QPushButton("Approve OCR")
        approve_btn.clicked.connect(self.approve)
        approval_layout.addWidget(approve_btn)
        
        reject_btn = QPushButton("Reject")
        reject_btn.clicked.connect(self.reject)
        approval_layout.addWidget(reject_btn)
        
        layout.addLayout(approval_layout)
    
    def run_ocr(self):
        """Run OCR on the current image."""
        if not self.controller.state.image_path:
            QMessageBox.warning(self, "Warning", "No image loaded")
            return
        
        # Show progress indicators
        self.run_ocr_btn.setEnabled(False)
        self.run_ocr_btn.setText("Running OCR...")
        
        # Show status label and progress bar
        self.ocr_status_label.setText("🔄 Running OCR... This may take a moment.")
        self.ocr_status_label.show()
        self.ocr_progress.show()
        
        # Disable other controls during OCR
        self.language_combo.setEnabled(False)
        self.show_grid_checkbox.setEnabled(False)
        
        # Clear previous results
        self.text_edit.clear()
        self.text_edit.setPlaceholderText("Running OCR... Please wait...")
        
        # Process events to update UI
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        
        try:
            # Get language from combo box
            language = self.language_combo.currentText()
            
            # Run OCR via controller
            results = self.controller.run_ocr(language=language)
            
            # Display results
            self.display_ocr_results(
                results['plaintext'],
                results['xml'],
                results['hocr']
            )
            
            # Update image display to show the actual image that was used for OCR
            self.update_ocr_image_display()
            
            # Hide progress indicators
            self.ocr_status_label.hide()
            self.ocr_progress.hide()
            
            # Re-enable controls
            self.run_ocr_btn.setEnabled(True)
            self.run_ocr_btn.setText("Run OCR")
            self.language_combo.setEnabled(True)
            self.show_grid_checkbox.setEnabled(True)
            
            # Show success message briefly
            self.ocr_status_label.setText("✅ OCR complete!")
            self.ocr_status_label.setStyleSheet("""
                QLabel {
                    background-color: #e8f5e9;
                    border: 2px solid #4caf50;
                    border-radius: 5px;
                    padding: 10px;
                    font-weight: bold;
                    color: #2e7d32;
                }
            """)
            self.ocr_status_label.show()
            
            # Hide success message after 3 seconds
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(3000, self.ocr_status_label.hide)
            
        except Exception as e:
            # Hide progress indicators
            self.ocr_status_label.hide()
            self.ocr_progress.hide()
            
            # Re-enable controls
            self.run_ocr_btn.setEnabled(True)
            self.run_ocr_btn.setText("Run OCR")
            self.language_combo.setEnabled(True)
            self.show_grid_checkbox.setEnabled(True)
            
            # Show error message
            self.text_edit.setPlaceholderText("OCR failed. Click 'Run OCR' to try again.")
            self.ocr_status_label.setText(f"❌ OCR failed: {str(e)}")
            self.ocr_status_label.setStyleSheet("""
                QLabel {
                    background-color: #ffebee;
                    border: 2px solid #f44336;
                    border-radius: 5px;
                    padding: 10px;
                    font-weight: bold;
                    color: #c62828;
                }
            """)
            self.ocr_status_label.show()
            
            QMessageBox.critical(self, "Error", f"OCR failed: {str(e)}")
    
    def display_ocr_results(self, plaintext_path: str, xml_path: str, hocr_path: str):
        """Display OCR results."""
        self.plaintext_path = plaintext_path
        self.xml_path = xml_path
        self.hocr_path = hocr_path
        
        # Clear placeholder
        self.text_edit.setPlaceholderText("")
        
        # Load plaintext
        if os.path.exists(plaintext_path):
            try:
                with open(plaintext_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self.text_edit.setPlainText(content)
            except Exception as e:
                self.text_edit.setPlainText(f"Error loading plaintext: {str(e)}")
        else:
            self.text_edit.setPlainText(f"Plaintext file not found: {plaintext_path}")
    
    def open_xml(self):
        """Open XML file location in file explorer/finder."""
        if hasattr(self, 'xml_path') and os.path.exists(self.xml_path):
            import subprocess
            import sys
            file_dir = os.path.dirname(os.path.abspath(self.xml_path))
            if sys.platform == 'darwin':
                subprocess.run(['open', file_dir])
            elif sys.platform.startswith('linux'):
                subprocess.run(['xdg-open', file_dir])
            elif sys.platform == 'win32':
                subprocess.run(['explorer', file_dir])
    
    def open_hocr(self):
        """Open hOCR file location in file explorer/finder."""
        if hasattr(self, 'hocr_path') and os.path.exists(self.hocr_path):
            import subprocess
            import sys
            file_dir = os.path.dirname(os.path.abspath(self.hocr_path))
            if sys.platform == 'darwin':
                subprocess.run(['open', file_dir])
            elif sys.platform.startswith('linux'):
                subprocess.run(['xdg-open', file_dir])
            elif sys.platform == 'win32':
                subprocess.run(['explorer', file_dir])
    
    def generate_tesseract_pdf(self):
        """Generate PDF from Tesseract."""
        # This would need to be implemented
        QMessageBox.information(self, "Info", "Tesseract PDF generation not yet implemented in GUI")
    
    def approve(self):
        """Approve OCR results."""
        # Text is display-only, so no need to save edited text
        # User can edit XML externally if needed
        self.approve_signal.emit()
    
    def reject(self):
        """Reject OCR results."""
        self.reject_signal.emit()
    
    def show_ocr_input_image(self):
        """Open the image file that was actually used for OCR in the system file viewer."""
        if hasattr(self.controller.state, 'ocr_input_image_path') and self.controller.state.ocr_input_image_path:
            image_path = self.controller.state.ocr_input_image_path
            if os.path.exists(image_path):
                import subprocess
                import sys
                if sys.platform == 'darwin':
                    subprocess.run(['open', image_path])
                elif sys.platform.startswith('linux'):
                    subprocess.run(['xdg-open', image_path])
                elif sys.platform == 'win32':
                    subprocess.run(['explorer', image_path])
            else:
                QMessageBox.warning(self, "Warning", f"OCR input image not found at: {image_path}")
        else:
            QMessageBox.warning(self, "Warning", "OCR input image path not available. Run OCR first.")
    
    def toggle_gridlines(self, state):
        """Toggle gridlines display on the image."""
        # Get the main window to access the image widget
        parent = self.parent()
        while parent and not hasattr(parent, 'ocr_image_widget'):
            parent = parent.parent()
        
        if parent and hasattr(parent, 'ocr_image_widget') and parent.ocr_image_widget:
            parent.ocr_image_widget.show_gridlines = (state == Qt.CheckState.Checked.value)
            parent.ocr_image_widget.update_display()
    
    def update_ocr_image_display(self):
        """Update the image display to show the image that was actually used for OCR."""
        # Get the main window to access the image widget
        parent = self.parent()
        while parent and not hasattr(parent, 'ocr_image_widget'):
            parent = parent.parent()
        
        if parent and hasattr(parent, 'controller'):
            # Prefer the OCR input image path (the actual image used for OCR)
            # Otherwise fall back to the controller's image path
            image_path = None
            if hasattr(parent.controller.state, 'ocr_input_image_path') and parent.controller.state.ocr_input_image_path:
                if os.path.exists(parent.controller.state.ocr_input_image_path):
                    image_path = parent.controller.state.ocr_input_image_path
            if not image_path:
                image_path = parent.controller.state.image_path
            
            if image_path and os.path.exists(image_path):
                from PIL import Image
                from PyQt6.QtWidgets import QScrollArea
                
                # Load the image
                img = Image.open(image_path)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Update or create the zoomable image widget
                if hasattr(parent, 'ocr_image_widget') and parent.ocr_image_widget:
                    parent.ocr_image_widget.original_image = img
                    parent.ocr_image_widget.zoom_factor = 1.0  # Reset to fit-to-height
                    parent.ocr_image_widget.update_display()
                else:
                    # Import here to avoid circular import
                    from gui.main_window import ZoomableImageWidget
                    # Create new scroll area and widget
                    scroll_area = QScrollArea()
                    scroll_area.setWidgetResizable(False)
                    scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    
                    zoomable_image = ZoomableImageWidget(img, scroll_area)
                    scroll_area.setWidget(zoomable_image)
                    
                    parent.ocr_image_widget = zoomable_image
                    parent.set_image_widget(scroll_area)


class LLMCleaningWidget(QWidget):
    """Widget for LLM text cleaning."""
    
    approve_signal = pyqtSignal()
    rerun_signal = pyqtSignal()
    
    def __init__(self, controller: PipelineController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.init_ui()
        self.load_existing_text()
    
    def init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        
        # Model selection
        model_group = QGroupBox("LLM Settings")
        model_layout = QVBoxLayout()
        
        model_select_layout = QHBoxLayout()
        model_select_layout.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        # Will be populated with available models
        self.model_combo.addItem("qwen2.5")
        model_select_layout.addWidget(self.model_combo)
        
        refresh_btn = QPushButton("Refresh Models")
        refresh_btn.clicked.connect(self.refresh_models)
        model_select_layout.addWidget(refresh_btn)
        model_layout.addLayout(model_select_layout)
        
        # Context input
        context_layout = QVBoxLayout()
        context_layout.addWidget(QLabel("Additional Context (optional):"))
        self.context_edit = QLineEdit()
        self.context_edit.setPlaceholderText("e.g., '1972 newspaper from New York'")
        context_layout.addWidget(self.context_edit)
        model_layout.addLayout(context_layout)
        
        model_group.setLayout(model_layout)
        layout.addWidget(model_group)
        
        # Buttons for running LLM or loading text manually
        button_layout = QHBoxLayout()
        run_btn = QPushButton("Run LLM Cleaning")
        run_btn.clicked.connect(self.run_cleaning)
        button_layout.addWidget(run_btn)
        
        load_text_btn = QPushButton("Load Text from File")
        load_text_btn.clicked.connect(self.load_text_from_file)
        button_layout.addWidget(load_text_btn)
        layout.addLayout(button_layout)
        
        # Output display
        layout.addWidget(QLabel("Cleaned Text (editable - you can paste or type text here):"))
        self.output_edit = QTextEdit()
        self.output_edit.setReadOnly(False)
        layout.addWidget(self.output_edit)
        
        # Approval buttons
        approval_layout = QHBoxLayout()
        
        approve_btn = QPushButton("Approve")
        approve_btn.clicked.connect(self.approve)
        approval_layout.addWidget(approve_btn)
        
        rerun_btn = QPushButton("Re-run LLM")
        rerun_btn.clicked.connect(self.rerun)
        approval_layout.addWidget(rerun_btn)
        
        layout.addLayout(approval_layout)
    
    def load_existing_text(self):
        """Load existing clean text or OCR plaintext into the editor."""
        # Prefer clean text if it exists
        if self.controller.state.clean_text:
            self.output_edit.setPlainText(self.controller.state.clean_text)
        elif self.controller.state.clean_text_path and os.path.exists(self.controller.state.clean_text_path):
            try:
                with open(self.controller.state.clean_text_path, 'r', encoding='utf-8') as f:
                    self.output_edit.setPlainText(f.read())
            except:
                pass
        elif self.controller.state.ocr_plaintext_path and os.path.exists(self.controller.state.ocr_plaintext_path):
            # Pre-populate with OCR plaintext as starting point
            try:
                with open(self.controller.state.ocr_plaintext_path, 'r', encoding='utf-8') as f:
                    self.output_edit.setPlainText(f.read())
            except:
                pass
    
    def refresh_models(self):
        """Refresh list of available Ollama models."""
        try:
            models = llm_cleaning.get_available_models()
            self.model_combo.clear()
            self.model_combo.addItems(models)
            if 'qwen2.5' in models:
                self.model_combo.setCurrentText('qwen2.5')
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Failed to get models: {str(e)}")
    
    def run_cleaning(self):
        """Run LLM cleaning."""
        if self.controller.state.ocr_plaintext_path is None:
            QMessageBox.warning(self, "Warning", "No OCR plaintext available")
            return
        
        model = self.model_combo.currentText()
        context = self.context_edit.text() if self.context_edit.text() else None
        
        try:
            # Run cleaning
            clean_path = self.controller.run_llm_cleaning(model, context)
            
            # Display result
            with open(clean_path, 'r', encoding='utf-8') as f:
                self.output_edit.setPlainText(f.read())
            
            QMessageBox.information(self, "Success", "LLM cleaning complete")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"LLM cleaning failed: {str(e)}")
    
    def load_text_from_file(self):
        """Load text from an external file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Text File",
            "",
            "Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self.output_edit.setPlainText(content)
                    QMessageBox.information(self, "Success", "Text loaded successfully")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load file: {str(e)}")
    
    def approve(self):
        """Save edited output and approve."""
        # Get text from the editor
        cleaned_text = self.output_edit.toPlainText()
        
        # Save to file if path exists, otherwise create one
        if not self.controller.state.clean_text_path:
            # Create a clean text path based on OCR plaintext path
            if self.controller.state.ocr_plaintext_path:
                base_name = os.path.splitext(os.path.basename(self.controller.state.ocr_plaintext_path))[0]
                base_name = base_name.replace('_plaintext', '')
                clean_text_path = os.path.join(
                    os.path.dirname(self.controller.state.ocr_plaintext_path),
                    f"{base_name}_cleantext.txt"
                )
                self.controller.state.clean_text_path = clean_text_path
        
        if self.controller.state.clean_text_path:
            os.makedirs(os.path.dirname(self.controller.state.clean_text_path) if os.path.dirname(self.controller.state.clean_text_path) else '.', exist_ok=True)
            with open(self.controller.state.clean_text_path, 'w', encoding='utf-8') as f:
                f.write(cleaned_text)
        
        # Update controller state
        self.controller.state.clean_text = cleaned_text
        
        self.approve_signal.emit()
    
    def rerun(self):
        """Re-run LLM cleaning."""
        self.rerun_signal.emit()
        self.run_cleaning()


class MappingReviewWidget(QWidget):
    """Widget for reviewing mapping results."""
    
    proceed_signal = pyqtSignal()
    mapping_updated = pyqtSignal()  # Emitted when hypothesis list is updated
    
    def __init__(self, controller: PipelineController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.hypothesis_list = None
        self.llm_elements = None
        self.init_ui()
    
    def init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        
        # Statistics
        self.stats_label = QLabel("No mapping data")
        layout.addWidget(self.stats_label)
        
        # Error list (will be populated)
        layout.addWidget(QLabel("Flagged Errors:"))
        self.error_list = QTextEdit()
        self.error_list.setReadOnly(True)
        layout.addWidget(self.error_list)
        
        # Re-run mapping button
        rerun_btn = QPushButton("Re-run Mapping")
        rerun_btn.clicked.connect(self.rerun_mapping)
        layout.addWidget(rerun_btn)
        
        # Proceed button
        proceed_btn = QPushButton("Proceed to PDF Generation")
        proceed_btn.clicked.connect(self.proceed)
        layout.addWidget(proceed_btn)
    
    def display_mapping_results(self, hypothesis_list, llm_elements=None, image_path=None, page=None):
        """Display mapping results with error highlighter."""
        self.hypothesis_list = hypothesis_list
        if llm_elements is not None:
            self.llm_elements = llm_elements
        
        matched = sum(1 for h in hypothesis_list if h.chosen_LLM_token is not None)
        errors = sum(1 for h in hypothesis_list if h.flagged_for_error)
        total = len(hypothesis_list)
        
        self.stats_label.setText(
            f"Matched: {matched}/{total} | Errors: {errors}"
        )
        
        # List errors
        error_text = []
        for i, hyp in enumerate(hypothesis_list):
            if hyp.flagged_for_error:
                alto_word = text_utils.decode_html_entities(hyp.anchor.content)
                error_text.append(f"Word {i}: '{alto_word}'")
        
        self.error_list.setPlainText("\n".join(error_text) if error_text else "No errors")
        
        # Create/update error highlighter if image and page are provided
        if image_path and page:
            # Remove existing error highlighter if any
            for i in range(self.layout().count()):
                item = self.layout().itemAt(i)
                if item and item.widget() and isinstance(item.widget(), ErrorHighlighter):
                    self.layout().removeWidget(item.widget())
                    item.widget().deleteLater()
            
            # Create new error highlighter
            self.error_highlighter = ErrorHighlighter(self)
            self.error_highlighter.load_image_and_errors(image_path, hypothesis_list, page)
            
            # Connect signals
            self.error_highlighter.word_corrected.connect(self.handle_word_correction)
            self.error_highlighter.words_merged.connect(self.handle_words_merge)
            self.error_highlighter.word_split.connect(self.handle_word_split)
            
            # Insert error highlighter at the top (before stats label)
            self.layout().insertWidget(0, self.error_highlighter)
    
    def handle_word_correction(self, hypothesis: TokenHypotheses, new_text: str):
        """Handle single word correction."""
        if self.llm_elements is None:
            # Create LLM elements from clean text if not available
            if self.controller.state.clean_text:
                self.llm_elements = create_LLM_element_list(self.controller.state.clean_text)
            else:
                QMessageBox.warning(self, "Warning", "No clean text available")
                return
        
        update_word_correction(hypothesis, new_text, self.llm_elements)
        self.display_mapping_results(self.hypothesis_list, self.llm_elements)
        self.mapping_updated.emit()
    
    def handle_words_merge(self, hypotheses: list, merged_text: str):
        """Handle merging multiple words into one."""
        if len(hypotheses) < 2:
            return
        
        if self.llm_elements is None:
            if self.controller.state.clean_text:
                self.llm_elements = create_LLM_element_list(self.controller.state.clean_text)
            else:
                QMessageBox.warning(self, "Warning", "No clean text available")
                return
        
        # Find or create matching LLM token
        matching_token = None
        for llm_token in self.llm_elements:
            if llm_token.word == merged_text and not llm_token.matched:
                matching_token = llm_token
                break
        
        if matching_token is None:
            # Create new LLM token
            matching_token = LLMToken(
                word=merged_text,
                word_normalized=text_utils.normalize_for_matching(merged_text)
            )
            self.llm_elements.append(matching_token)
        
        # Get all ALTO words from selected hypotheses
        all_alto_words = []
        for hyp in hypotheses:
            if hyp.candidates and hyp.chosen_index is not None:
                chosen_cand = hyp.candidates[hyp.chosen_index]
                all_alto_words.extend(chosen_cand.alto_words)
            else:
                all_alto_words.append(hyp.anchor)
        
        # Create combined candidate
        combined_candidate = TokenCandidate(
            clean_form=text_utils.normalize_for_matching(merged_text),
            kind="word",
            alto_words=all_alto_words,
            fuzzy_score=100.0  # Manual merge gets perfect score
        )
        combined_candidate.possible_llm_elements_by_fuzzy_match = [matching_token]
        
        # Use first hypothesis as the anchor, remove others
        first_hyp = hypotheses[0]
        first_hyp.candidates = [combined_candidate]
        first_hyp.chosen_index = 0
        first_hyp.chosen_LLM_token = matching_token
        first_hyp.flagged_for_error = False
        matching_token.matched = True
        
        # Remove other hypotheses from the list
        for hyp in hypotheses[1:]:
            if hyp in self.hypothesis_list:
                self.hypothesis_list.remove(hyp)
        
        # Update neighbors
        if len(hypotheses) > 0:
            # Set left neighbor from first hypothesis's left
            if hypotheses[0].anchor.before_word:
                for h in self.hypothesis_list:
                    if h.anchor == hypotheses[0].anchor.before_word:
                        first_hyp.left_matched = h
                        h.right_matched = first_hyp
                        break
            
            # Set right neighbor from last hypothesis's right
            if hypotheses[-1].anchor.after_word:
                for h in self.hypothesis_list:
                    if h.anchor == hypotheses[-1].anchor.after_word:
                        first_hyp.right_matched = h
                        h.left_matched = first_hyp
                        break
        
        self.display_mapping_results(self.hypothesis_list, self.llm_elements)
        self.mapping_updated.emit()
    
    def handle_word_split(self, hypothesis: TokenHypotheses, split_texts: list):
        """Handle splitting one word into multiple."""
        if len(split_texts) < 2:
            return
        
        if self.llm_elements is None:
            if self.controller.state.clean_text:
                self.llm_elements = create_LLM_element_list(self.controller.state.clean_text)
            else:
                QMessageBox.warning(self, "Warning", "No clean text available")
                return
        
        # Import split function
        from word_merges import _create_split_hypotheses
        clean_vocab = set(e.word_normalized for e in self.llm_elements)
        
        # Create split hypotheses
        split_hypotheses = _create_split_hypotheses(
            hypothesis.anchor,
            split_texts,
            clean_vocab,
            fuzzy_cutoff=90.0
        )
        
        if not split_hypotheses:
            QMessageBox.warning(self, "Warning", "Failed to create split hypotheses")
            return
        
        # Find or create LLM tokens for split words
        for i, split_hyp in enumerate(split_hypotheses):
            split_text = split_texts[i]
            
            # Find matching LLM token
            matching_token = None
            for llm_token in self.llm_elements:
                if llm_token.word == split_text and not llm_token.matched:
                    matching_token = llm_token
                    break
            
            if matching_token is None:
                # Create new LLM token
                matching_token = LLMToken(
                    word=split_text,
                    word_normalized=text_utils.normalize_for_matching(split_text)
                )
                self.llm_elements.append(matching_token)
            
            # Assign to split hypothesis
            split_hyp.chosen_LLM_token = matching_token
            matching_token.matched = True
            split_hyp.flagged_for_error = False
            
            # Find matching candidate
            for j, cand in enumerate(split_hyp.candidates):
                if cand.clean_form == text_utils.normalize_for_matching(split_text):
                    split_hyp.chosen_index = j
                    break
        
        # Replace original hypothesis with split hypotheses
        original_index = self.hypothesis_list.index(hypothesis)
        self.hypothesis_list.remove(hypothesis)
        
        # Insert split hypotheses at original position
        for i, split_hyp in enumerate(split_hypotheses):
            self.hypothesis_list.insert(original_index + i, split_hyp)
        
        # Update neighbors for split hypotheses
        for i, split_hyp in enumerate(split_hypotheses):
            if i > 0:
                split_hyp.left_matched = split_hypotheses[i - 1]
                split_hypotheses[i - 1].right_matched = split_hyp
            elif hypothesis.left_matched:
                split_hyp.left_matched = hypothesis.left_matched
                if hypothesis.left_matched:
                    hypothesis.left_matched.right_matched = split_hyp
            
            if i < len(split_hypotheses) - 1:
                split_hyp.right_matched = split_hypotheses[i + 1]
            elif hypothesis.right_matched:
                split_hyp.right_matched = hypothesis.right_matched
                if hypothesis.right_matched:
                    hypothesis.right_matched.left_matched = split_hyp
        
        self.display_mapping_results(self.hypothesis_list, self.llm_elements)
        self.mapping_updated.emit()
    
    def rerun_mapping(self):
        """Re-run mapping after manual corrections."""
        if self.controller.state.ocr_xml_path and self.controller.state.clean_text:
            try:
                hypothesis_list, page = self.controller.run_mapping(show_ocr_accuracy=False)
                self.display_mapping_results(hypothesis_list)
                self.mapping_updated.emit()
                QMessageBox.information(self, "Success", "Mapping re-run complete")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to re-run mapping: {str(e)}")
    
    def proceed(self):
        """Proceed to next stage."""
        self.proceed_signal.emit()


class PDFGenerationWidget(QWidget):
    """Widget for PDF generation."""
    
    generate_signal = pyqtSignal(str)
    
    def __init__(self, controller: PipelineController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.init_ui()
    
    def init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("PDF Generation"))
        
        # Output path
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Output Path:"))
        self.path_edit = QLineEdit()
        path_layout.addWidget(self.path_edit)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_path)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)
        
        # Generate button
        generate_btn = QPushButton("Generate PDF")
        generate_btn.clicked.connect(self.generate)
        layout.addWidget(generate_btn)
    
    def browse_path(self):
        """Browse for output path."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PDF",
            "",
            "PDF Files (*.pdf);;All Files (*)"
        )
        if path:
            self.path_edit.setText(path)
    
    def generate(self):
        """Generate PDF."""
        output_path = self.path_edit.text()
        if not output_path:
            QMessageBox.warning(self, "Warning", "Please specify output path")
            return
        
        self.generate_signal.emit(output_path)

