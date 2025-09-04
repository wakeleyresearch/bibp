"""
Production GUI for BibP
Advanced interface with real-time monitoring, extraction analysis, and comprehensive controls.
"""

import sys
import os
import time
import json
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QTextEdit, QPushButton, QListWidget, QListWidgetItem, QLabel,
    QProgressBar, QGroupBox, QSplitter, QFileDialog, QMessageBox,
    QTabWidget, QTableWidget, QTableWidgetItem, QCheckBox, QSpinBox,
    QComboBox, QStatusBar, QMenuBar, QMenu, QScrollArea, QFrame,
    QGridLayout, QSlider, QToolButton, QButtonGroup
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSettings
from PyQt6.QtGui import (
    QDragEnterEvent, QDropEvent, QFont, QColor, QPalette, 
    QAction, QIcon, QPixmap
)

import logging
from config import config
from extractor import extract_references, analyze_extraction_quality
from downloader import download_references_parallel

logger = logging.getLogger(__name__)

@dataclass
class ProcessingStats:
    """Statistics tracking for processing session."""
    total_files: int = 0
    references_extracted: int = 0
    references_downloaded: int = 0
    sources_used: Dict[str, int] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    def __post_init__(self):
        if self.sources_used is None:
            self.sources_used = {}

class ExtractionAnalysisThread(QThread):
    """Thread for analyzing reference extraction quality."""
    analysis_complete = pyqtSignal(dict)
    update_log = pyqtSignal(str)
    
    def __init__(self, pdf_path: str):
        super().__init__()
        self.pdf_path = pdf_path
    
    def run(self):
        try:
            self.update_log.emit(f"🔍 Analyzing reference extraction from {Path(self.pdf_path).name}...")
            
            references = extract_references(self.pdf_path)
            analysis = analyze_extraction_quality(references)
            
            self.analysis_complete.emit({
                'pdf_path': self.pdf_path,
                'references': references,
                'analysis': analysis
            })
            
        except Exception as e:
            self.update_log.emit(f"❌ Analysis failed: {str(e)}")
            logger.error(f"Analysis error: {e}")

class ProcessingThread(QThread):
    """Enhanced processing thread with detailed progress."""
    update_log = pyqtSignal(str)
    update_progress = pyqtSignal(int, int)  # current, total
    reference_processed = pyqtSignal(str, str, str)  # filename, status, source
    file_complete = pyqtSignal(str, int, int)  # filename, success_count, total_count
    finished = pyqtSignal()
    error_occurred = pyqtSignal(str)
    stats_updated = pyqtSignal(dict)

    def __init__(self, pdf_files: List[str], extraction_method: str = 'auto'):
        super().__init__()
        self.pdf_files = pdf_files
        self.extraction_method = extraction_method
        self.should_stop = False
        self.stats = ProcessingStats(total_files=len(pdf_files))
        self.stats.start_time = time.time()

    def run(self):
        try:
            for file_idx, pdf_path in enumerate(self.pdf_files, 1):
                if self.should_stop:
                    break
                
                try:
                    self.update_progress.emit(file_idx - 1, len(self.pdf_files))
                    self.update_log.emit(f"📖 Processing {Path(pdf_path).name}...")
                    
                    # Extract references
                    extraction_method = None if self.extraction_method == 'auto' else self.extraction_method
                    references = extract_references(pdf_path, force_method=extraction_method)
                    
                    self.stats.references_extracted += len(references)
                    
                    if not references:
                        self.update_log.emit("   ⚠️ No references found - skipping")
                        self.file_complete.emit(Path(pdf_path).name, 0, 0)
                        continue
                    
                    # Analyze extraction quality
                    analysis = analyze_extraction_quality(references)
                    quality_score = analysis.get('quality_score', 0.0)
                    
                    self.update_log.emit(f"   📊 Found {len(references)} references (quality: {quality_score:.2f})")
                    
                    # Download PDFs
                    self.update_log.emit(f"   🔍 Searching for PDFs...")
                    statuses = download_references_parallel(references, pdf_path)
                    
                    # Parse results
                    success_count = 0
                    for status in statuses:
                        if status.startswith("✅"):
                            success_count += 1
                            # Extract source information
                            if "(from " in status:
                                source = status.split("(from ")[1].split(")")[0]
                                self.stats.sources_used[source] = self.stats.sources_used.get(source, 0) + 1
                        
                        # Emit individual reference result
                        if status.startswith(("✅", "❌", "📄")):
                            parts = status.split(" ", 2)
                            if len(parts) >= 2:
                                filename = parts[1]
                                source = ""
                                if "(from " in status:
                                    source = status.split("(from ")[1].split(")")[0]
                                elif "already exists" in status:
                                    source = "existing"
                                
                                self.reference_processed.emit(filename, parts[0], source)
                        
                        # Log all statuses
                        if status.strip():
                            self.update_log.emit(f"   {status}")
                    
                    self.stats.references_downloaded += success_count
                    self.file_complete.emit(Path(pdf_path).name, success_count, len(references))
                    self.update_log.emit("")
                    
                except Exception as e:
                    error_msg = f"❌ Error processing {Path(pdf_path).name}: {str(e)}"
                    self.update_log.emit(error_msg)
                    logger.error(f"Processing error: {e}")
                    self.file_complete.emit(Path(pdf_path).name, 0, 0)
            
            self.stats.end_time = time.time()
            self.update_progress.emit(len(self.pdf_files), len(self.pdf_files))
            
            # Emit final statistics
            stats_dict = {
                'total_files': self.stats.total_files,
                'references_extracted': self.stats.references_extracted,
                'references_downloaded': self.stats.references_downloaded,
                'sources_used': self.stats.sources_used,
                'duration': self.stats.end_time - self.stats.start_time if self.stats.start_time else 0
            }
            self.stats_updated.emit(stats_dict)
            
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            self.finished.emit()

    def stop(self):
        self.should_stop = True

class ConfigurationWidget(QWidget):
    """Widget for managing BibP configuration."""
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.load_config()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Extraction settings
        extraction_group = QGroupBox("Reference Extraction")
        extraction_layout = QVBoxLayout()
        
        method_layout = QHBoxLayout()
        method_layout.addWidget(QLabel("Method:"))
        
        self.extraction_method = QComboBox()
        self.extraction_method.addItems(["auto", "grobid", "refextract"])
        self.extraction_method.setCurrentText("auto")
        method_layout.addWidget(self.extraction_method)
        
        extraction_layout.addLayout(method_layout)
        
        # GROBID status
        self.grobid_status = QLabel()
        self.update_grobid_status()
        extraction_layout.addWidget(self.grobid_status)
        
        extraction_group.setLayout(extraction_layout)
        layout.addWidget(extraction_group)
        
        # Processing settings
        processing_group = QGroupBox("Processing")
        processing_layout = QVBoxLayout()
        
        threads_layout = QHBoxLayout()
        threads_layout.addWidget(QLabel("Max Threads:"))
        
        self.max_threads = QSpinBox()
        self.max_threads.setRange(1, 100)
        self.max_threads.setValue(config.max_threads)
        threads_layout.addWidget(self.max_threads)
        
        processing_layout.addLayout(threads_layout)
        processing_group.setLayout(processing_layout)
        layout.addWidget(processing_group)
        
        # API settings
        api_group = QGroupBox("API Configuration")
        api_layout = QVBoxLayout()
        
        self.api_checkboxes = {}
        for api_name, api_config in config.apis.items():
            checkbox = QCheckBox(f"{api_name} ({api_config.rate_limit}/s)")
            checkbox.setChecked(api_config.enabled)
            self.api_checkboxes[api_name] = checkbox
            api_layout.addWidget(checkbox)
        
        api_group.setLayout(api_layout)
        layout.addWidget(api_group)
        
        # Contact info
        contact_group = QGroupBox("Contact Information")
        contact_layout = QVBoxLayout()
        
        self.contact_email = QLabel(f"Email: {config.contact_email}")
        contact_layout.addWidget(self.contact_email)
        
        self.s2_key_status = QLabel(f"S2 API Key: {'✅ Present' if config.semantic_scholar_api_key else '❌ Missing'}")
        contact_layout.addWidget(self.s2_key_status)
        
        contact_group.setLayout(contact_layout)
        layout.addWidget(contact_group)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def update_grobid_status(self):
        if config.grobid_enabled:
            try:
                from grobid_client import grobid_client
                if grobid_client and grobid_client.is_alive:
                    self.grobid_status.setText(f"GROBID: ✅ Connected ({config.grobid_url})")
                    self.grobid_status.setStyleSheet("color: green;")
                else:
                    self.grobid_status.setText(f"GROBID: ❌ Not responding ({config.grobid_url})")
                    self.grobid_status.setStyleSheet("color: red;")
            except Exception:
                self.grobid_status.setText("GROBID: ❌ Error connecting")
                self.grobid_status.setStyleSheet("color: red;")
        else:
            self.grobid_status.setText("GROBID: ❌ Disabled")
            self.grobid_status.setStyleSheet("color: orange;")
    
    def load_config(self):
        self.extraction_method.setCurrentText("auto")
        self.max_threads.setValue(config.max_threads)
    
    def get_settings(self) -> Dict[str, Any]:
        return {
            'extraction_method': self.extraction_method.currentText(),
            'max_threads': self.max_threads.value(),
            'enabled_apis': [name for name, checkbox in self.api_checkboxes.items() if checkbox.isChecked()]
        }

class ResultsWidget(QWidget):
    """Widget for displaying processing results and statistics."""
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.processing_stats = None
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Summary statistics
        self.stats_label = QLabel("No processing completed yet")
        self.stats_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(self.stats_label)
        
        # Results table
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(["File", "References", "Downloaded", "Success Rate"])
        self.results_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.results_table)
        
        # Source breakdown
        sources_group = QGroupBox("Source Breakdown")
        self.sources_layout = QVBoxLayout()
        self.sources_label = QLabel("No data yet")
        self.sources_layout.addWidget(self.sources_label)
        sources_group.setLayout(self.sources_layout)
        layout.addWidget(sources_group)
        
        self.setLayout(layout)
    
    def update_stats(self, stats: Dict[str, Any]):
        self.processing_stats = stats
        
        # Update summary
        duration = stats.get('duration', 0)
        success_rate = (stats['references_downloaded'] / max(1, stats['references_extracted'])) * 100
        
        summary_text = (
            f"📊 Processed {stats['total_files']} files in {duration:.1f}s\n"
            f"📚 {stats['references_extracted']} references extracted, "
            f"{stats['references_downloaded']} downloaded ({success_rate:.1f}% success)"
        )
        self.stats_label.setText(summary_text)
        
        # Update source breakdown
        sources_used = stats.get('sources_used', {})
        if sources_used:
            sources_text = "Sources used:\n"
            total_downloads = sum(sources_used.values())
            
            for source, count in sorted(sources_used.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / total_downloads) * 100
                sources_text += f"• {source}: {count} ({percentage:.1f}%)\n"
            
            self.sources_label.setText(sources_text.strip())
        else:
            self.sources_label.setText("No successful downloads")
    
    def add_file_result(self, filename: str, success_count: int, total_count: int):
        row_position = self.results_table.rowCount()
        self.results_table.insertRow(row_position)
        
        success_rate = (success_count / max(1, total_count)) * 100
        
        self.results_table.setItem(row_position, 0, QTableWidgetItem(filename))
        self.results_table.setItem(row_position, 1, QTableWidgetItem(str(total_count)))
        self.results_table.setItem(row_position, 2, QTableWidgetItem(str(success_count)))
        self.results_table.setItem(row_position, 3, QTableWidgetItem(f"{success_rate:.1f}%"))
        
        # Color code success rates
        color = QColor(0, 150, 0) if success_rate > 70 else QColor(200, 100, 0) if success_rate > 30 else QColor(150, 0, 0)
        self.results_table.item(row_position, 3).setForeground(color)

class MainWindow(QMainWindow):
    """Enhanced main window with tabbed interface and advanced features."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BibP - Reference PDF Retriever v2.0 (Production)")
        self.setGeometry(100, 100, 1000, 700)
        self.setAcceptDrops(True)
        
        self.pdf_files = []
        self.processing_thread = None
        self.analysis_thread = None
        
        self.setup_ui()
        self.setup_menu_bar()
        self.setup_status_bar()
        self.load_settings()
        
        # Validate configuration on startup
        self.validate_configuration()
    
    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        
        # Main tab widget
        self.tab_widget = QTabWidget()
        
        # Files tab
        files_tab = self.create_files_tab()
        self.tab_widget.addTab(files_tab, "📁 Files & Processing")
        
        # Configuration tab
        self.config_widget = ConfigurationWidget()
        self.tab_widget.addTab(self.config_widget, "⚙️ Configuration")
        
        # Results tab
        self.results_widget = ResultsWidget()
        self.tab_widget.addTab(self.results_widget, "📊 Results")
        
        layout.addWidget(self.tab_widget)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.analyze_button = QPushButton("🔍 Analyze Selected")
        self.analyze_button.clicked.connect(self.analyze_selected)
        self.analyze_button.setEnabled(False)
        button_layout.addWidget(self.analyze_button)
        
        self.start_button = QPushButton("🚀 Start Processing")
        self.start_button.clicked.connect(self.start_processing)
        self.start_button.setEnabled(False)
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        button_layout.addWidget(self.start_button)
        
        self.stop_button = QPushButton("⏹️ Stop")
        self.stop_button.clicked.connect(self.stop_processing)
        self.stop_button.setEnabled(False)
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 12px 24px;
                font-size: 14px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
        """)
        button_layout.addWidget(self.stop_button)
        
        button_layout.addStretch()
        
        self.open_output_button = QPushButton("📁 Open Output")
        self.open_output_button.clicked.connect(self.open_output_folder)
        self.open_output_button.setEnabled(False)
        button_layout.addWidget(self.open_output_button)
        
        layout.addLayout(button_layout)
    
    def create_files_tab(self):
        files_widget = QWidget()
        layout = QVBoxLayout(files_widget)
        
        # File management section
        file_group = QGroupBox("PDF Files")
        file_layout = QVBoxLayout(file_group)
        
        # File list
        self.pdf_list = QListWidget()
        self.pdf_list.setToolTip("Drag and drop PDF files here, or use the Add Files button")
        self.pdf_list.itemChanged.connect(self.update_button_states)
        file_layout.addWidget(self.pdf_list)
        
        # File management buttons
        file_buttons = QHBoxLayout()
        
        self.add_files_button = QPushButton("📄 Add Files...")
        self.add_files_button.clicked.connect(self.add_files)
        file_buttons.addWidget(self.add_files_button)
        
        self.clear_files_button = QPushButton("🗑️ Clear List")
        self.clear_files_button.clicked.connect(self.clear_file_list)
        file_buttons.addWidget(self.clear_files_button)
        
        self.select_all_button = QPushButton("☑️ Select All")
        self.select_all_button.clicked.connect(self.select_all_files)
        file_buttons.addWidget(self.select_all_button)
        
        file_buttons.addStretch()
        
        self.file_count_label = QLabel("0 files, 0 selected")
        file_buttons.addWidget(self.file_count_label)
        
        file_layout.addLayout(file_buttons)
        layout.addWidget(file_group)
        
        # Progress section
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        progress_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Ready to process PDFs")
        progress_layout.addWidget(self.status_label)
        
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)
        
        # Log section
        log_group = QGroupBox("Processing Log")
        log_layout = QVBoxLayout(log_group)
        
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setFont(QFont("Consolas", 9))
        self.log_area.setStyleSheet("""
            QTextEdit {
                background-color: #f8f8f8;
                border: 1px solid #ddd;
                color: #333;
            }
        """)
        log_layout.addWidget(self.log_area)
        
        log_buttons = QHBoxLayout()
        
        self.clear_log_button = QPushButton("🗑️ Clear Log")
        self.clear_log_button.clicked.connect(self.log_area.clear)
        log_buttons.addWidget(self.clear_log_button)
        
        self.save_log_button = QPushButton("💾 Save Log")
        self.save_log_button.clicked.connect(self.save_log)
        log_buttons.addWidget(self.save_log_button)
        
        log_buttons.addStretch()
        log_layout.addLayout(log_buttons)
        
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        return files_widget
    
    def setup_menu_bar(self):
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('File')
        
        add_files_action = QAction('Add PDF Files...', self)
        add_files_action.triggered.connect(self.add_files)
        file_menu.addAction(add_files_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction('Exit', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Tools menu
        tools_menu = menubar.addMenu('Tools')
        
        validate_config_action = QAction('Validate Configuration', self)
        validate_config_action.triggered.connect(self.validate_configuration)
        tools_menu.addAction(validate_config_action)
        
        test_apis_action = QAction('Test API Connectivity', self)
        test_apis_action.triggered.connect(self.test_apis)
        tools_menu.addAction(test_apis_action)
        
        # Help menu
        help_menu = menubar.addMenu('Help')
        
        about_action = QAction('About BibP', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def setup_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Show configuration status
        api_count = len(config.get_enabled_apis())
        grobid_status = "GROBID ✅" if config.grobid_enabled else "GROBID ❌"
        
        self.status_bar.showMessage(f"Ready | {api_count} APIs enabled | {grobid_status}")
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()
    
    def dropEvent(self, event: QDropEvent):
        files = [url.toLocalFile() for url in event.mimeData().urls() 
                if url.toLocalFile().lower().endswith(".pdf")]
        
        if files:
            self.add_pdf_files(files)
            self.log_area.append(f"📁 Added {len(files)} PDF files via drag & drop")
        else:
            self.log_area.append("⚠️ No valid PDF files found in drop")
    
    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select PDF Files", "", "PDF Files (*.pdf)"
        )
        
        if files:
            self.add_pdf_files(files)
            self.log_area.append(f"📁 Added {len(files)} PDF files")
    
    def add_pdf_files(self, file_paths: List[str]):
        added_count = 0
        for file_path in file_paths:
            if file_path not in self.pdf_files:
                self.pdf_files.append(file_path)
                
                item = QListWidgetItem(os.path.basename(file_path))
                item.setCheckState(Qt.CheckState.Checked)
                item.setToolTip(file_path)
                item.setData(Qt.ItemDataRole.UserRole, file_path)
                self.pdf_list.addItem(item)
                
                added_count += 1
        
        self.update_button_states()
        
        if added_count == 0:
            self.log_area.append("ℹ️ All files were already in the list")
    
    def clear_file_list(self):
        self.pdf_list.clear()
        self.pdf_files.clear()
        self.update_button_states()
        self.log_area.append("🗑️ File list cleared")
    
    def select_all_files(self):
        for i in range(self.pdf_list.count()):
            item = self.pdf_list.item(i)
            item.setCheckState(Qt.CheckState.Checked)
        self.update_button_states()
    
    def update_button_states(self):
        total_files = self.pdf_list.count()
        selected_files = sum(1 for i in range(total_files) 
                           if self.pdf_list.item(i).checkState() == Qt.CheckState.Checked)
        
        self.file_count_label.setText(f"{total_files} files, {selected_files} selected")
        
        has_selection = selected_files > 0
        not_processing = self.processing_thread is None
        
        self.start_button.setEnabled(has_selection and not_processing)
        self.analyze_button.setEnabled(has_selection and not_processing)
    
    def analyze_selected(self):
        selected_files = self.get_selected_files()
        if not selected_files:
            return
        
        # For now, analyze first selected file
        pdf_path = selected_files[0]
        
        self.analysis_thread = ExtractionAnalysisThread(pdf_path)
        self.analysis_thread.analysis_complete.connect(self.show_analysis_results)
        self.analysis_thread.update_log.connect(self.log_area.append)
        self.analysis_thread.start()
        
        self.analyze_button.setEnabled(False)
    
    def show_analysis_results(self, analysis_data):
        analysis = analysis_data['analysis']
        references = analysis_data['references']
        
        # Create analysis dialog
        msg = QMessageBox(self)
        msg.setWindowTitle("Reference Extraction Analysis")
        msg.setIcon(QMessageBox.Icon.Information)
        
        text = f"""
Quality Score: {analysis['quality_score']:.2f}/1.0

Statistics:
• Total references: {analysis['total_references']}
• References with titles: {analysis['percentages']['has_title']:.1f}%
• References with DOIs: {analysis['percentages']['has_doi']:.1f}%
• References with authors: {analysis['percentages']['has_authors']:.1f}%

Recommendation:
{analysis['recommendation']}
"""
        
        if analysis['issues']:
            text += f"\nIssues:\n• " + "\n• ".join(analysis['issues'])
        
        msg.setText(text)
        msg.exec()
        
        self.analyze_button.setEnabled(True)
    
    def get_selected_files(self) -> List[str]:
        selected = []
        for i in range(self.pdf_list.count()):
            item = self.pdf_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                file_path = item.data(Qt.ItemDataRole.UserRole)
                selected.append(file_path)
        return selected
    
    def start_processing(self):
        selected_files = self.get_selected_files()
        if not selected_files:
            self.log_area.append("⚠️ No files selected for processing")
            return
        
        # Get settings from config widget
        settings = self.config_widget.get_settings()
        
        self.log_area.clear()
        self.log_area.append(f"🚀 Starting processing of {len(selected_files)} files...")
        self.log_area.append(f"⚙️ Extraction method: {settings['extraction_method']}")
        self.log_area.append(f"⚙️ Max threads: {settings['max_threads']}")
        self.log_area.append("")
        
        # Update configuration
        config.max_threads = settings['max_threads']
        
        # Start processing thread
        self.processing_thread = ProcessingThread(selected_files, settings['extraction_method'])
        self.processing_thread.update_log.connect(self.log_area.append)
        self.processing_thread.update_progress.connect(self.update_progress)
        self.processing_thread.file_complete.connect(self.results_widget.add_file_result)
        self.processing_thread.stats_updated.connect(self.results_widget.update_stats)
        self.processing_thread.finished.connect(self.processing_finished)
        self.processing_thread.error_occurred.connect(self.processing_error)
        self.processing_thread.start()
        
        # Update UI state
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.open_output_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(selected_files))
        self.progress_bar.setValue(0)
        
        self.tab_widget.setCurrentIndex(0)  # Switch to processing tab
    
    def stop_processing(self):
        if self.processing_thread:
            self.log_area.append("🛑 Stopping processing...")
            self.processing_thread.stop()
    
    def update_progress(self, current: int, total: int):
        self.progress_bar.setValue(current)
        self.status_label.setText(f"Processing file {current + 1} of {total}")
    
    def processing_finished(self):
        self.log_area.append("✅ Processing completed!")
        
        # Update UI state
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.open_output_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Processing complete")
        
        self.processing_thread = None
        
        # Switch to results tab
        self.tab_widget.setCurrentIndex(2)
    
    def processing_error(self, error_msg: str):
        self.log_area.append(f"❌ Critical error: {error_msg}")
        QMessageBox.critical(self, "Processing Error", f"An error occurred:\n{error_msg}")
        
        # Reset UI state
        self.processing_finished()
    
    def open_output_folder(self):
        if self.pdf_files:
            first_pdf = Path(self.pdf_files[0])
            output_dir = first_pdf.parent / f"{first_pdf.stem}{config.output_dir_suffix}"
            
            if output_dir.exists():
                if sys.platform == "win32":
                    os.startfile(output_dir)
                elif sys.platform == "darwin":
                    os.system(f"open '{output_dir}'")
                else:
                    os.system(f"xdg-open '{output_dir}'")
            else:
                QMessageBox.information(self, "No Output", "No output folder found yet.")
    
    def save_log(self):
        log_content = self.log_area.toPlainText()
        if not log_content:
            QMessageBox.information(self, "No Log", "No log content to save.")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Log File", f"bibp_log_{int(time.time())}.txt", "Text Files (*.txt)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(log_content)
                self.log_area.append(f"💾 Log saved to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save log:\n{str(e)}")
    
    def validate_configuration(self):
        is_valid, warnings = config.validate()
        
        if warnings:
            msg = "Configuration Validation:\n\n" + "\n".join(warnings)
            if is_valid:
                QMessageBox.information(self, "Configuration", msg)
            else:
                QMessageBox.warning(self, "Configuration Issues", msg)
        else:
            QMessageBox.information(self, "Configuration", "✅ Configuration is valid!")
    
    def test_apis(self):
        # This would run the API test script
        QMessageBox.information(self, "API Test", 
                              "API connectivity test would be run here.\n"
                              "For now, check the console logs for API status.")
    
    def show_about(self):
        about_text = """
BibP - Reference PDF Retriever v2.0

A comprehensive tool for automatically downloading academic PDFs from references.

Features:
• GROBID integration for superior reference extraction
• Multi-API support (arXiv, OpenAlex, Semantic Scholar, PubMed, etc.)
• Intelligent rate limiting and error handling
• Real-time processing monitoring
• Comprehensive statistics and analysis

APIs Supported: arXiv, Unpaywall, OpenAlex, Semantic Scholar, Crossref, PubMed/PMC, CORE

Contact: Built with ❤️ for researchers
        """
        QMessageBox.about(self, "About BibP", about_text)
    
    def load_settings(self):
        # Load settings from QSettings if needed
        pass
    
    def closeEvent(self, event):
        if self.processing_thread and self.processing_thread.isRunning():
            reply = QMessageBox.question(self, "Exit Confirmation", 
                                       "Processing is still running. Exit anyway?")
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            
            self.processing_thread.stop()
        
        event.accept()

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("BibP")
    app.setApplicationVersion("2.0")
    
    # Set application style
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()